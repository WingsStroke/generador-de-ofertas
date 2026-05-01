from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from typing import List
import json
import shutil
import tempfile
from datetime import datetime

from models import (
    ProcessedSchedule, UploadResponse, BlockUpdate, Subject
)
from utils.schedule_processor import ScheduleProcessor
from utils.export_helper import export_to_json_format

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

DICCIONARIO_PATH = ROOT_DIR / "diccionario_ingenieria_de_sistemas.json"
subject_dict = {}

if DICCIONARIO_PATH.exists():
    with open(DICCIONARIO_PATH, 'r', encoding='utf-8') as f:
        subject_dict = json.load(f)

processor = ScheduleProcessor(subject_dict)

from utils.subject_matcher import SubjectMatcher
subject_matcher = SubjectMatcher(subject_dict)

@api_router.get("/")
async def root():
    return {"message": "Academic Schedule Processor API"}

@api_router.post("/upload", response_model=UploadResponse)
async def upload_schedule(file: UploadFile = File(...)):
    """Sube y procesa un archivo XLSX"""
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos Excel (.xlsx, .xls)")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
        shutil.copyfileobj(file.file, tmp_file)
        tmp_path = tmp_file.name
    
    try:
        schedule = processor.process_file(tmp_path, file.filename)
        
        schedule_dict = schedule.model_dump()
        schedule_dict['fecha_procesamiento'] = schedule_dict['fecha_procesamiento'].isoformat()
        
        await db.schedules.insert_one(schedule_dict)
        
        return UploadResponse(
            schedule_id=schedule.id,
            message="Archivo procesado exitosamente",
            confianza_global=schedule.nivel_confianza_global
        )
    
    except Exception as e:
        logging.error(f"Error procesando archivo: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error procesando archivo: {str(e)}")
    
    finally:
        os.unlink(tmp_path)

@api_router.get("/schedules")
async def get_schedules():
    """Lista todos los horarios procesados"""
    schedules = await db.schedules.find({}, {"_id": 0}).to_list(1000)
    return schedules

@api_router.get("/schedule/{schedule_id}")
async def get_schedule(schedule_id: str):
    """Obtiene un horario específico con todos sus detalles"""
    schedule = await db.schedules.find_one({"id": schedule_id}, {"_id": 0})
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    
    return schedule

@api_router.put("/schedule/{schedule_id}/cell/{dia}/{hora_inicio}/block/{block_id}")
async def update_block(
    schedule_id: str,
    dia: str,
    hora_inicio: str,
    block_id: str,
    update: BlockUpdate
):
    """Actualiza un bloque específico"""
    schedule = await db.schedules.find_one({"id": schedule_id}, {"_id": 0})
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    
    updated = False
    for cell in schedule["celdas"]:
        if cell["dia"] == dia and cell["hora_inicio"] == hora_inicio:
            for block in cell["bloques"]:
                if block["id"] == block_id:
                    if update.materia is not None:
                        block["materia"] = update.materia
                    if update.materia_id is not None:
                        block["materia_id"] = update.materia_id
                    if update.grupo is not None:
                        block["grupo"] = update.grupo
                    if update.docente is not None:
                        block["docente"] = update.docente
                    if update.aula is not None:
                        block["aula"] = update.aula
                    
                    block["estado"] = "confirmed"
                    block["nivel_confianza"] = 1.0
                    updated = True
                    break
            if updated:
                break
    
    if not updated:
        raise HTTPException(status_code=404, detail="Bloque no encontrado")
    
    await db.schedules.update_one(
        {"id": schedule_id},
        {"$set": {"celdas": schedule["celdas"]}}
    )
    
    return {"message": "Bloque actualizado exitosamente"}

@api_router.delete("/schedule/{schedule_id}/cell/{dia}/{hora_inicio}/block/{block_id}")
async def delete_block(
    schedule_id: str,
    dia: str,
    hora_inicio: str,
    block_id: str
):
    """Elimina un bloque específico"""
    schedule = await db.schedules.find_one({"id": schedule_id}, {"_id": 0})
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    
    updated = False
    for cell in schedule["celdas"]:
        if cell["dia"] == dia and cell["hora_inicio"] == hora_inicio:
            cell["bloques"] = [b for b in cell["bloques"] if b["id"] != block_id]
            updated = True
            break
    
    if not updated:
        raise HTTPException(status_code=404, detail="Bloque no encontrado")
    
    await db.schedules.update_one(
        {"id": schedule_id},
        {"$set": {"celdas": schedule["celdas"]}}
    )
    
    return {"message": "Bloque eliminado exitosamente"}

@api_router.post("/schedule/{schedule_id}/export")
async def export_schedule(schedule_id: str):
    """Exporta el horario al formato JSON especificado"""
    schedule = await db.schedules.find_one({"id": schedule_id}, {"_id": 0})
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    
    exported = export_to_json_format(schedule, subject_dict)
    
    return JSONResponse(content=exported)

@api_router.get("/subjects", response_model=List[Subject])
async def get_subjects():
    """Obtiene el diccionario de materias"""
    subjects = []
    for subject_id, data in subject_dict.items():
        subjects.append(Subject(
            id=subject_id,
            nombre_oficial=data["nombre_oficial"],
            codigo=data.get("codigo"),
            creditos=data.get("creditos")
        ))
    return subjects

@api_router.get("/subjects/search/{query}")
async def search_subjects(query: str, limit: int = 10):
    """Busca materias por texto con fuzzy matching"""
    suggestions = subject_matcher.get_suggestions(query, limit=limit)
    
    results = []
    for subject_id, name, confidence in suggestions:
        results.append({
            "id": subject_id,
            "nombre": name,
            "confidence": confidence,
            "codigo": subject_dict[subject_id].get("codigo"),
            "creditos": subject_dict[subject_id].get("creditos")
        })
    
    return results

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
