from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from typing import List, Dict, Any
import json
import shutil
import tempfile
from datetime import datetime

from pydantic import BaseModel
from models import (
    ProcessedSchedule, UploadResponse, BlockUpdate, BlockMove, Subject, ProgramaAcademico
)
from utils.schedule_processor import ScheduleProcessor


class BulkBlockUpdate(BaseModel):
    block_ids: List[str]
    update: BlockUpdate
from utils.export_helper import export_to_json_format

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

DICCIONARIOS_DIR = ROOT_DIR / "diccionarios"
programas_dict = {}
processors = {}

def load_academic_programs():
    """Carga todos los programas académicos disponibles"""
    global programas_dict, processors
    
    if not DICCIONARIOS_DIR.exists():
        logging.warning(f"Directorio de diccionarios no encontrado: {DICCIONARIOS_DIR}")
        return
    
    programa_names = {
        "ingenieria_de_sistemas": "Ingeniería de Sistemas",
        "ingenieria_de_alimentos": "Ingeniería de Alimentos",
        "ingenieria_civil": "Ingeniería Civil",
        "ingenieria_quimica": "Ingeniería Química"
    }
    
    for dict_file in DICCIONARIOS_DIR.glob("*.json"):
        programa_id = dict_file.stem
        
        try:
            with open(dict_file, 'r', encoding='utf-8') as f:
                subject_dict = json.load(f)
            
            programas_dict[programa_id] = {
                "id": programa_id,
                "nombre": programa_names.get(programa_id, programa_id.replace("_", " ").title()),
                "diccionario": subject_dict,
                "total_materias": len(subject_dict)
            }
            
            processors[programa_id] = ScheduleProcessor(subject_dict)
            
            logging.info(f"Programa cargado: {programa_id} con {len(subject_dict)} materias")
        
        except Exception as e:
            logging.error(f"Error cargando programa {programa_id}: {str(e)}")

load_academic_programs()

if not programas_dict:
    logging.warning("No se cargaron programas académicos")

@api_router.get("/")
async def root():
    return {"message": "Academic Schedule Processor API", "programs": len(programas_dict)}

@api_router.get("/programs", response_model=List[ProgramaAcademico])
async def get_programs():
    """Obtiene la lista de programas académicos disponibles"""
    programs = []
    for prog_id, prog_data in programas_dict.items():
        programs.append(ProgramaAcademico(
            id=prog_id,
            nombre=prog_data["nombre"],
            total_materias=prog_data["total_materias"]
        ))
    return programs

@api_router.post("/upload", response_model=UploadResponse)
async def upload_schedule(file: UploadFile = File(...), program_id: str = "ingenieria_de_sistemas"):
    """Sube y procesa un archivo XLSX"""
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos Excel (.xlsx, .xls)")
    
    if program_id not in programas_dict:
        raise HTTPException(status_code=400, detail=f"Programa '{program_id}' no encontrado")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
        shutil.copyfileobj(file.file, tmp_file)
        tmp_path = tmp_file.name
    
    try:
        processor = processors[program_id]
        programa_nombre = programas_dict[program_id]["nombre"]
        schedule = processor.process_file(tmp_path, file.filename, program_id, programa_nombre)
        
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

def _iter_celdas_collections(schedule: Dict) -> List[List[Dict]]:
    """Devuelve todas las listas de celdas de un schedule (top-level + cada hoja)."""
    collections = []
    if schedule.get("celdas"):
        collections.append(schedule["celdas"])
    hojas_data = schedule.get("hojas_data") or {}
    for hoja_info in hojas_data.values():
        if isinstance(hoja_info, dict) and hoja_info.get("celdas"):
            collections.append(hoja_info["celdas"])
    return collections

def _find_block_locations(schedule: Dict, block_id: str):
    """Busca TODAS las ocurrencias de un bloque (puede estar duplicado en celdas + hojas_data).
    Devuelve lista de tuplas (cell, block, celdas_list).
    """
    matches = []
    for celdas in _iter_celdas_collections(schedule):
        for cell in celdas:
            for block in cell.get("bloques", []):
                if block.get("id") == block_id:
                    matches.append((cell, block, celdas))
    return matches

@api_router.put("/schedule/{schedule_id}/cell/{dia}/{hora_inicio}/block/{block_id}")
async def update_block(
    schedule_id: str,
    dia: str,
    hora_inicio: str,
    block_id: str,
    update: BlockUpdate
):
    """Actualiza un bloque específico (busca en todas las hojas)"""
    schedule = await db.schedules.find_one({"id": schedule_id}, {"_id": 0})

    if not schedule:
        raise HTTPException(status_code=404, detail="Horario no encontrado")

    cell, block, _celdas = (None, None, None)
    matches = _find_block_locations(schedule, block_id)
    if matches:
        cell, block, _celdas = matches[0]

    if not block:
        raise HTTPException(status_code=404, detail="Bloque no encontrado")

    for _c, blk, _cl in matches:
        if update.materia is not None:
            blk["materia"] = update.materia
        if update.materia_id is not None:
            blk["materia_id"] = update.materia_id
        if update.grupo is not None:
            blk["grupo"] = update.grupo
        if update.docente is not None:
            blk["docente"] = update.docente
        if update.aula is not None:
            blk["aula"] = update.aula
        blk["estado"] = "confirmed"
        blk["nivel_confianza"] = 1.0

    await db.schedules.update_one(
        {"id": schedule_id},
        {"$set": {"celdas": schedule["celdas"], "hojas_data": schedule.get("hojas_data", {})}}
    )

    return {"message": "Bloque actualizado exitosamente"}

@api_router.delete("/schedule/{schedule_id}/cell/{dia}/{hora_inicio}/block/{block_id}")
async def delete_block(
    schedule_id: str,
    dia: str,
    hora_inicio: str,
    block_id: str
):
    """Elimina un bloque específico (busca en todas las hojas)"""
    schedule = await db.schedules.find_one({"id": schedule_id}, {"_id": 0})

    if not schedule:
        raise HTTPException(status_code=404, detail="Horario no encontrado")

    matches = _find_block_locations(schedule, block_id)

    if not matches:
        raise HTTPException(status_code=404, detail="Bloque no encontrado")

    for cell, _blk, _cl in matches:
        cell["bloques"] = [b for b in cell["bloques"] if b["id"] != block_id]

    await db.schedules.update_one(
        {"id": schedule_id},
        {"$set": {"celdas": schedule["celdas"], "hojas_data": schedule.get("hojas_data", {})}}
    )

    return {"message": "Bloque eliminado exitosamente"}

@api_router.patch("/schedule/{schedule_id}/blocks/bulk")
async def bulk_update_blocks(schedule_id: str, payload: BulkBlockUpdate):
    """Actualiza múltiples bloques con los mismos campos. Solo se aplican campos no nulos."""
    schedule = await db.schedules.find_one({"id": schedule_id}, {"_id": 0})

    if not schedule:
        raise HTTPException(status_code=404, detail="Horario no encontrado")

    update = payload.update
    not_found = []
    updated_ids = set()

    for block_id in payload.block_ids:
        matches = _find_block_locations(schedule, block_id)
        if not matches:
            not_found.append(block_id)
            continue
        for _c, blk, _cl in matches:
            if update.materia is not None:
                blk["materia"] = update.materia
            if update.materia_id is not None:
                blk["materia_id"] = update.materia_id
            if update.grupo is not None:
                blk["grupo"] = update.grupo
            if update.docente is not None:
                blk["docente"] = update.docente
            if update.aula is not None:
                blk["aula"] = update.aula
            blk["estado"] = "confirmed"
            blk["nivel_confianza"] = 1.0
        updated_ids.add(block_id)

    if updated_ids:
        await db.schedules.update_one(
            {"id": schedule_id},
            {"$set": {"celdas": schedule["celdas"], "hojas_data": schedule.get("hojas_data", {})}}
        )

    return {
        "message": f"{len(updated_ids)} bloque(s) actualizado(s)",
        "updated": list(updated_ids),
        "not_found": not_found,
    }

@api_router.post("/schedule/{schedule_id}/export")
async def export_schedule(schedule_id: str):
    """Exporta el horario al formato JSON especificado"""
    schedule = await db.schedules.find_one({"id": schedule_id}, {"_id": 0})
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    
    program_id = schedule.get("programa_id", "ingenieria_de_sistemas")
    subject_dict = programas_dict.get(program_id, {}).get("diccionario", {})
    
    exported = export_to_json_format(schedule, subject_dict)
    
    return JSONResponse(content=exported)

@api_router.put("/schedule/{schedule_id}/block/{block_id}/horarios")
async def update_block_horarios(
    schedule_id: str,
    block_id: str,
    horarios: List[Dict]
):
    """Actualiza los horarios de un bloque específico"""
    from utils.time_utils import calcular_bloques_horarios, validar_solapamiento
    
    schedule = await db.schedules.find_one({"id": schedule_id}, {"_id": 0})
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    
    matches = _find_block_locations(schedule, block_id)

    if not matches:
        raise HTTPException(status_code=404, detail="Bloque no encontrado")

    horarios_procesados = []
    for horario in horarios:
        bloques_cant, minutos = calcular_bloques_horarios(
            horario["hora_inicio"],
            horario["hora_fin"]
        )

        horarios_procesados.append({
            "dia": horario["dia"],
            "hora_inicio": horario["hora_inicio"],
            "hora_fin": horario["hora_fin"],
            "bloques_cantidad": bloques_cant
        })

    for _c, blk, _cl in matches:
        blk["horarios"] = horarios_procesados

    await db.schedules.update_one(
        {"id": schedule_id},
        {"$set": {"celdas": schedule["celdas"], "hojas_data": schedule.get("hojas_data", {})}}
    )
    
    return {
        "message": "Horarios actualizados exitosamente",
        "block_id": block_id,
        "horarios": horarios_procesados
    }

@api_router.get("/schedule/{schedule_id}/search")
async def search_in_schedule(
    schedule_id: str,
    q: str,
    type: str = "all",
    limit: int = 50
):
    """Busca materia/docente/aula en todas las hojas del horario"""
    from rapidfuzz import fuzz
    
    schedule = await db.schedules.find_one({"id": schedule_id}, {"_id": 0})
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    
    if not q or len(q) < 2:
        return {"results": [], "total": 0, "query": q}
    
    results = []
    query_lower = q.lower()
    
    hojas_data = schedule.get("hojas_data", {})
    
    if not hojas_data:
        celdas = schedule.get("celdas", [])
        hojas_data = {schedule.get("hoja_actual", "Hoja 1"): {"celdas": celdas}}
    
    for hoja_nombre, hoja_info in hojas_data.items():
        for celda in hoja_info.get("celdas", []):
            for bloque in celda.get("bloques", []):
                score = 0
                matched_field = None
                matched_value = None
                
                if type in ["all", "materia"]:
                    materia = bloque.get("materia", "")
                    if materia:
                        materia_score = fuzz.partial_ratio(query_lower, materia.lower())
                        if materia_score > score:
                            score = materia_score
                            matched_field = "materia"
                            matched_value = materia
                
                if type in ["all", "docente"]:
                    docente = bloque.get("docente", "")
                    if docente:
                        docente_score = fuzz.partial_ratio(query_lower, docente.lower())
                        if docente_score > score:
                            score = docente_score
                            matched_field = "docente"
                            matched_value = docente
                
                if type in ["all", "aula"]:
                    aula = bloque.get("aula", "")
                    if aula:
                        aula_score = fuzz.partial_ratio(query_lower, aula.lower())
                        if aula_score > score:
                            score = aula_score
                            matched_field = "aula"
                            matched_value = aula
                
                if score >= 60:
                    results.append({
                        "hoja": hoja_nombre,
                        "dia": celda["dia"],
                        "hora_inicio": celda["hora_inicio"],
                        "hora_fin": celda["hora_fin"],
                        "bloque": {
                            "id": bloque["id"],
                            "materia": bloque.get("materia"),
                            "grupo": bloque.get("grupo"),
                            "docente": bloque.get("docente"),
                            "aula": bloque.get("aula"),
                            "estado": bloque.get("estado")
                        },
                        "matched_field": matched_field,
                        "matched_value": matched_value,
                        "score": score
                    })
    
    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:limit]
    
    hojas_con_resultados = len(set(r["hoja"] for r in results))
    
    return {
        "results": results,
        "total": len(results),
        "hojas_con_resultados": hojas_con_resultados,
        "query": q,
        "type": type
    }

@api_router.post("/schedule/{schedule_id}/move-block")
async def move_block(schedule_id: str, move: BlockMove):
    """Mueve un bloque a una nueva celda (drag & drop)"""
    schedule = await db.schedules.find_one({"id": schedule_id}, {"_id": 0})
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    
    block_found = None
    from_cell = None
    target_celdas = None  # la lista de celdas (hoja) donde vive el bloque

    for celdas in _iter_celdas_collections(schedule):
        for cell in celdas:
            if cell["dia"] == move.from_dia and cell["hora_inicio"] == move.from_hora_inicio:
                for block in cell["bloques"]:
                    if block["id"] == move.block_id:
                        block_found = block
                        from_cell = cell
                        target_celdas = celdas
                        break
            if block_found:
                break
        if block_found:
            break

    if not block_found:
        raise HTTPException(status_code=404, detail="Bloque no encontrado")

    from_cell["bloques"] = [b for b in from_cell["bloques"] if b["id"] != move.block_id]

    to_cell = None
    for cell in target_celdas:
        if cell["dia"] == move.to_dia and cell["hora_inicio"] == move.to_hora_inicio:
            to_cell = cell
            break

    if not to_cell:
        to_cell = {
            "dia": move.to_dia,
            "hora_inicio": move.to_hora_inicio,
            "hora_fin": move.to_hora_fin,
            "bloques": [],
            "celda_ref": None
        }
        target_celdas.append(to_cell)

    to_cell["bloques"].append(block_found)

    await db.schedules.update_one(
        {"id": schedule_id},
        {"$set": {"celdas": schedule["celdas"], "hojas_data": schedule.get("hojas_data", {})}}
    )

    return {"message": "Bloque movido exitosamente", "block_id": move.block_id}

@api_router.get("/subjects", response_model=List[Subject])
async def get_subjects(program_id: str = "ingenieria_de_sistemas"):
    """Obtiene el diccionario de materias de un programa específico"""
    if program_id not in programas_dict:
        raise HTTPException(status_code=400, detail=f"Programa '{program_id}' no encontrado")
    
    subject_dict = programas_dict[program_id]["diccionario"]
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
async def search_subjects(query: str, program_id: str = "ingenieria_de_sistemas", limit: int = 10):
    """Busca materias por texto con fuzzy matching en un programa específico"""
    if program_id not in programas_dict:
        raise HTTPException(status_code=400, detail=f"Programa '{program_id}' no encontrado")
    
    from utils.subject_matcher import SubjectMatcher
    subject_dict = programas_dict[program_id]["diccionario"]
    matcher = SubjectMatcher(subject_dict)
    suggestions = matcher.get_suggestions(query, limit=limit)
    
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
