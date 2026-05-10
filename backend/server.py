from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# MONGODB-READY: Import de MongoDB preservado para reactivación futura
# from motor.motor_asyncio import AsyncIOMotorClient

import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import shutil
import tempfile
from datetime import datetime
import asyncio
from typing import Union

from pydantic import BaseModel
from models import (
    ProcessedSchedule, UploadResponse, BlockUpdate, BlockMove, Subject, ProgramaAcademico
)
from utils.schedule_processor import ScheduleProcessor

# Nuevo sistema de storage (reemplaza MongoDB temporalmente)
from storage import storage

# Configurar logging ANTES de cargar programas
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class BulkBlockUpdate(BaseModel):
    block_ids: List[str]
    update: BlockUpdate


class BlockCreate(BaseModel):
    sheet: str
    dia: str
    hora_inicio: str
    hora_fin: str
    materia: Optional[str] = None
    materia_id: Optional[str] = None
    grupo: Optional[str] = None
    docente: Optional[str] = None
    aula: Optional[str] = None
from utils.export_helper import export_to_json_format

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MONGODB-READY: Conexión a MongoDB preservada para reactivación futura
# mongo_url = os.environ['MONGO_URL']
# client = AsyncIOMotorClient(mongo_url)
# db = client[os.environ['DB_NAME']]

# Inicializar rate limiter
limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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

# Tamaño máximo de archivo: 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024

# Firmas mágicas de archivos Excel
EXCEL_SIGNATURES = {
    b'\x50\x4B\x03\x04': 'xlsx',  # ZIP (XLSX es un ZIP)
    b'\xD0\xCF\x11\xE0': 'xls',   # OLE Compound Document (XLS antiguo)
}

ALLOWED_MIME_TYPES = {
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # .xlsx
    'application/vnd.ms-excel',  # .xls
    'application/octet-stream',  # Algunos navegadores envían esto
}


async def validate_excel_file(file: UploadFile) -> tuple[bool, str]:
    """
    Valida que el archivo sea un Excel genuino verificando:
    1. Tamaño máximo
    2. Firma mágica (magic bytes)
    3. Que pueda abrirse con openpyxl
    
    Returns:
        (is_valid, error_message)
    """
    # Leer primeros 4KB para verificar firma y tamaño
    content = await file.read(4096)
    
    # Verificar que hayamos leído algo
    if len(content) < 4:
        return False, "Archivo vacío o demasiado pequeño"
    
    # Verificar firma mágica
    is_valid_signature = False
    for signature, fmt in EXCEL_SIGNATURES.items():
        if content.startswith(signature):
            is_valid_signature = True
            break
    
    if not is_valid_signature:
        return False, "El archivo no tiene formato Excel válido (firma mágica inválida)"
    
    # Verificar tipo MIME si está disponible
    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        # Algunos navegadores envían application/octet-stream, eso está OK
        if file.content_type != 'application/octet-stream':
            return False, f"Tipo de archivo no permitido: {file.content_type}"
    
    # Intentar abrir con openpyxl para verificar que es un Excel válido
    await file.seek(0)
    tmp_path = None
    try:
        # Leer todo el contenido para verificar tamaño
        full_content = await file.read()
        
        if len(full_content) > MAX_FILE_SIZE:
            return False, f"Archivo demasiado grande (máx {MAX_FILE_SIZE // (1024*1024)}MB)"
        
        # Guardar temporalmente y verificar con openpyxl
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            tmp.write(full_content)
            tmp_path = tmp.name
        
        # Intentar cargar con openpyxl
        try:
            import openpyxl
            wb = openpyxl.load_workbook(tmp_path, data_only=True, read_only=True)
            sheet_names = wb.sheetnames
            wb.close()
            
            if not sheet_names:
                return False, "El archivo Excel no contiene hojas"
            
        except Exception as e:
            return False, f"El archivo no es un Excel válido: {str(e)}"
        
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
        
        # Resetear el puntero del archivo para procesamiento posterior
        await file.seek(0)
        return True, ""
        
    except Exception as e:
        return False, f"Error validando archivo: {str(e)}"


@api_router.post("/upload", response_model=UploadResponse)
@limiter.limit("5/minute")
async def upload_schedule(request: Request, file: UploadFile = File(...), program_id: str = "ingenieria_de_sistemas"):
    """
    Sube y procesa un archivo XLSX.
    
    Rate limit: 5 uploads por minuto por IP.
    El archivo es validado por firma mágica, tipo MIME y estructura Excel real.
    """
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos Excel (.xlsx, .xls)")
    
    # Validar contenido real del archivo
    is_valid, error_msg = await validate_excel_file(file)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Archivo inválido: {error_msg}")
    
    if program_id not in programas_dict:
        raise HTTPException(status_code=400, detail=f"Programa '{program_id}' no encontrado")
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
        shutil.copyfileobj(file.file, tmp_file)
        tmp_path = tmp_file.name
    
    tmp_path_for_cleanup = tmp_path  # Guardar para cleanup
    
    try:
        processor = processors[program_id]
        programa_nombre = programas_dict[program_id]["nombre"]
        schedule = processor.process_file(tmp_path, file.filename, program_id, programa_nombre)
        
        schedule_dict = schedule.model_dump()
        schedule_dict['fecha_procesamiento'] = schedule_dict['fecha_procesamiento'].isoformat()
        
        # Agregar campos de versionado para optimistic locking
        schedule_dict['_v'] = 0
        
        # MONGODB-READY: Reemplazado por storage.create()
        # await db.schedules.insert_one(schedule_dict)
        await storage.create(schedule_dict)
        
        return UploadResponse(
            schedule_id=schedule.id,
            message="Archivo procesado exitosamente",
            confianza_global=schedule.nivel_confianza_global
        )
    
    except HTTPException:
        # Re-lanzar excepciones HTTP sin modificar
        raise
    
    except Exception as e:
        logging.error(f"Error procesando archivo: {str(e)}", exc_info=True)
        # No exponer detalles internos al cliente
        raise HTTPException(
            status_code=500, 
            detail="Error interno al procesar el archivo. Por favor intente nuevamente o contacte soporte."
        )
    
    finally:
        # Asegurar limpieza del archivo temporal
        if tmp_path_for_cleanup and os.path.exists(tmp_path_for_cleanup):
            try:
                os.unlink(tmp_path_for_cleanup)
            except OSError as e:
                logging.warning(f"No se pudo eliminar archivo temporal {tmp_path_for_cleanup}: {e}")

@api_router.post("/import-json")
async def import_json_schedule(request: Request):
    """
    Importa un horario desde el JSON exportado previamente.
    Valida la estructura, convierte al formato interno y devuelve un nuevo schedule_id.
    """
    import uuid
    from datetime import timezone

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="El archivo no es un JSON válido")

    # --- Validación de estructura ---
    errors = []
    if "metadata" not in data:
        errors.append("Falta la sección 'metadata'")
    if "semestres" not in data:
        errors.append("Falta la sección 'semestres'")
    else:
        if not isinstance(data["semestres"], list):
            errors.append("'semestres' debe ser una lista")
        else:
            for i, sem in enumerate(data["semestres"]):
                if not isinstance(sem, dict):
                    errors.append(f"semestres[{i}]: debe ser un objeto")
                    continue
                if "numero" not in sem:
                    errors.append(f"semestres[{i}]: falta 'numero'")
                if "asignaturas" not in sem or not isinstance(sem.get("asignaturas"), list):
                    errors.append(f"semestres[{i}]: falta 'asignaturas' (lista)")
                    continue
                for j, asig in enumerate(sem.get("asignaturas", [])):
                    if not isinstance(asig, dict):
                        errors.append(f"semestres[{i}].asignaturas[{j}]: debe ser un objeto")
                        continue
                    for campo in ("id", "nombre", "grupos"):
                        if campo not in asig:
                            errors.append(f"semestres[{i}].asignaturas[{j}]: falta '{campo}'")
                    for k, grp in enumerate(asig.get("grupos", [])):
                        if not isinstance(grp, dict):
                            errors.append(f"semestres[{i}].asignaturas[{j}].grupos[{k}]: debe ser un objeto")
                            continue
                        for campo in ("id", "grupo", "horarios"):
                            if campo not in grp:
                                errors.append(f"semestres[{i}].asignaturas[{j}].grupos[{k}]: falta '{campo}'")
                        for h, hor in enumerate(grp.get("horarios", [])):
                            for campo in ("dia", "inicio", "fin"):
                                if campo not in hor:
                                    errors.append(
                                        f"semestres[{i}].asignaturas[{j}].grupos[{k}].horarios[{h}]: falta '{campo}'"
                                    )

    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "El JSON tiene errores de estructura", "errors": errors}
        )

    # --- Conversión al formato interno ---
    meta = data.get("metadata", {})
    programa_nombre = meta.get("programa", "Programa importado")
    nombre_archivo = meta.get("archivo", "importado.json")
    fecha = meta.get("fechaProcesamiento", datetime.now(timezone.utc).isoformat())

    # Determinar programa_id por nombre
    programa_id = "ingenieria_de_sistemas"
    for pid, pdata in programas_dict.items():
        if pdata["nombre"].lower() in programa_nombre.lower() or programa_nombre.lower() in pdata["nombre"].lower():
            programa_id = pid
            break

    # Obtener datos de preview si el JSON fue exportado con _raw_preview_data
    preview_data = data.get("_raw_preview_data", {})

    # Construir hojas_data: cada semestre → una hoja "Table N"
    hojas_data = {}
    all_celdas = []

    for sem in data["semestres"]:
        num = sem.get("numero", 0)
        sheet_name = f"Table {num}" if num > 0 else "Table 1"
        celdas = []

        for asig in sem.get("asignaturas", []):
            materia_id = asig["id"]
            materia_nombre = asig["nombre"]
            creditos = asig.get("creditos")
            for grp in asig.get("grupos", []):
                grupo_label = grp.get("grupo", "")
                docente = grp.get("profesor")
                aula = grp.get("ubicacion")
                for hor in grp.get("horarios", []):
                    dia = hor["dia"]
                    hora_inicio = hor["inicio"]
                    hora_fin = hor["fin"]

                    existing = next(
                        (c for c in celdas if c["dia"] == dia and c["hora_inicio"] == hora_inicio and c["hora_fin"] == hora_fin),
                        None
                    )
                    bloque = {
                        "id": str(uuid.uuid4()),
                        "materia": materia_nombre,
                        "materia_id": materia_id,
                        "grupo": grupo_label,
                        "docente": docente,
                        "aula": aula,
                        "creditos": creditos,
                        "horarios": [{"dia": dia, "hora_inicio": hora_inicio, "hora_fin": hora_fin, "bloques_cantidad": 1}],
                        "nivel_confianza": 1.0,
                        "estado": "confirmed",
                    }
                    if existing:
                        existing["bloques"].append(bloque)
                    else:
                        celdas.append({
                            "dia": dia,
                            "hora_inicio": hora_inicio,
                            "hora_fin": hora_fin,
                            "celda_ref": f"{dia}_{hora_inicio}",
                            "bloques": [bloque],
                        })

        # Usar datos de preview del JSON exportado si están disponibles
        sheet_preview = preview_data.get(sheet_name, {})
        hojas_data[sheet_name] = {
            "nombre": sheet_name,
            "celdas": celdas,
            "estructura_dias": sheet_preview.get("estructura_dias", []),
            "estructura_horas": sheet_preview.get("estructura_horas", []),
            "excel_preview": sheet_preview.get("excel_preview", []),
            "nivel_confianza": 1.0,
        }
        all_celdas.extend(celdas)

    first_sheet = list(hojas_data.keys())[0] if hojas_data else "Table 1"
    first_celdas = hojas_data[first_sheet]["celdas"] if hojas_data else []
    first_sheet_data = hojas_data.get(first_sheet, {}) if hojas_data else {}

    schedule_id = str(uuid.uuid4())
    schedule_dict = {
        "id": schedule_id,
        "nombre_archivo": nombre_archivo,
        "fecha_procesamiento": fecha,
        "programa_id": programa_id,
        "programa_nombre": programa_nombre,
        "programa": programa_nombre,
        "hoja_actual": first_sheet,
        "hojas": list(hojas_data.keys()),
        "hojas_data": hojas_data,
        "celdas": first_celdas,
        "estructura_dias": first_sheet_data.get("estructura_dias", []),
        "estructura_horas": first_sheet_data.get("estructura_horas", []),
        "excel_preview": first_sheet_data.get("excel_preview", []),
        "nivel_confianza_global": 1.0,
        "_v": 0,
    }

    await storage.create(schedule_dict)

    return {
        "schedule_id": schedule_id,
        "message": "JSON importado exitosamente",
        "semestres": len(data["semestres"]),
        "programa": programa_nombre,
    }


@api_router.get("/schedules")
async def get_schedules():
    """Lista todos los horarios procesados"""
    # MONGODB-READY: Reemplazado por storage.list_all()
    # schedules = await db.schedules.find({}, {"_id": 0}).to_list(1000)
    schedules = await storage.list_all(1000)
    return schedules

@api_router.get("/schedule/{schedule_id}")
async def get_schedule(schedule_id: str):
    """Obtiene un horario específico con todos sus detalles"""
    # MONGODB-READY: Reemplazado por storage.get()
    # schedule = await db.schedules.find_one({"id": schedule_id}, {"_id": 0})
    schedule = await storage.get(schedule_id)
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    
    return schedule

async def _atomic_update_with_retry(
    schedule_id: str,
    update_fn,
    max_retries: int = 3,
    backoff_ms: float = 50.0
) -> Dict:
    """
    Ejecuta una actualización atómica.
    
    Con el storage en memoria, el locking ya es manejado internamente por storage.update().
    Esta función mantiene la misma interfaz para compatibilidad futura con MongoDB.
    
    Args:
        schedule_id: ID del horario
        update_fn: Función que recibe el schedule y devuelve (updated_schedule, result_data)
        max_retries: Número máximo de reintentos
        backoff_ms: Tiempo base entre reintentos (ms)
    
    Returns:
        result_data de la función update_fn
    
    Raises:
        HTTPException(404) si no se encuentra el horario
    """
    # MONGODB-READY: Con MongoDB se usaría optimistic locking manual
    # Con storage en memoria, el locking es manejado internamente por storage.update()
    
    # NOTA: wrapped_update_fn NO debe ser async porque storage.update() llama a update_fn sin await
    def wrapped_update_fn(data: Dict) -> None:
        """Wrapper que ejecuta update_fn y captura el resultado."""
        nonlocal result_data
        _updated_data, result_data = update_fn(data)
        # Los cambios ya se aplican in-place a data dentro de update_fn.
        # NO hacer data.clear()/data.update() porque _updated_data es el mismo
        # objeto que data, y data.clear() lo vaciaría antes de data.update().
    
    result_data = None
    
    # Ejecutar actualización atómica usando storage
    success = await storage.update(schedule_id, wrapped_update_fn)
    
    if not success:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    
    return result_data


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

def _update_block_in_schedule(schedule: Dict, block_id: str, update: BlockUpdate) -> int:
    """
    Actualiza un bloque en todas las colecciones de celdas del schedule.
    Retorna el número de bloques actualizados.
    """
    matches = _find_block_locations(schedule, block_id)
    
    if not matches:
        return 0
    
    updated_count = 0
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
        blk["_updated_at"] = datetime.utcnow().isoformat()
        updated_count += 1
    
    return updated_count


@api_router.put("/schedule/{schedule_id}/cell/{dia}/{hora_inicio}/block/{block_id}")
@limiter.limit("60/minute")
async def update_block(
    request: Request,
    schedule_id: str,
    dia: str,
    hora_inicio: str,
    block_id: str,
    update: BlockUpdate
):
    """
    Actualiza un bloque específico (busca en todas las hojas) con optimistic locking.
    
    Esta operación es atómica y segura para concurrencia. Si hay conflictos,
    se reintenta automáticamente hasta 3 veces.
    
    Rate limit: 60 actualizaciones por minuto por IP.
    """
    def do_update(schedule: Dict) -> tuple:
        updated_count = _update_block_in_schedule(schedule, block_id, update)
        
        if updated_count == 0:
            raise HTTPException(status_code=404, detail="Bloque no encontrado")
        
        result = {
            "message": "Bloque actualizado exitosamente",
            "block_id": block_id,
            "updated_locations": updated_count
        }
        
        return schedule, result
    
    return await _atomic_update_with_retry(schedule_id, do_update)

def _delete_block_from_schedule(schedule: Dict, block_id: str) -> int:
    """
    Elimina un bloque de todas las colecciones de celdas del schedule.
    Retorna el número de ubicaciones de donde fue eliminado.
    """
    matches = _find_block_locations(schedule, block_id)
    
    if not matches:
        return 0
    
    deleted_count = 0
    for cell, _blk, _cl in matches:
        original_len = len(cell.get("bloques", []))
        cell["bloques"] = [b for b in cell["bloques"] if b.get("id") != block_id]
        if len(cell["bloques"]) < original_len:
            deleted_count += 1
    
    return deleted_count


@api_router.delete("/schedule/{schedule_id}/cell/{dia}/{hora_inicio}/block/{block_id}")
@limiter.limit("60/minute")
async def delete_block(
    request: Request,
    schedule_id: str,
    dia: str,
    hora_inicio: str,
    block_id: str
):
    """
    Elimina un bloque específico (busca en todas las hojas) con optimistic locking.
    
    Esta operación es atómica y segura para concurrencia. Si hay conflictos,
    se reintenta automáticamente hasta 3 veces.
    
    Rate limit: 60 eliminaciones por minuto por IP.
    """
    def do_delete(schedule: Dict) -> tuple:
        deleted_count = _delete_block_from_schedule(schedule, block_id)
        
        if deleted_count == 0:
            raise HTTPException(status_code=404, detail="Bloque no encontrado")
        
        result = {
            "message": "Bloque eliminado exitosamente",
            "block_id": block_id,
            "deleted_from_locations": deleted_count
        }
        
        return schedule, result
    
    return await _atomic_update_with_retry(schedule_id, do_delete)

@api_router.post("/schedule/{schedule_id}/block")
async def create_block(schedule_id: str, payload: BlockCreate):
    """Crea un nuevo bloque en la celda indicada (día/hora) de una hoja específica.

    Si la celda aún no existe, se crea. Si la hoja indicada es `hoja_actual`, también
    se sincroniza con el array top-level `celdas`.
    """
    import uuid
    from utils.time_utils import calcular_bloques_horarios

    bloques_cantidad, _ = calcular_bloques_horarios(payload.hora_inicio, payload.hora_fin)
    new_block = {
        "id": str(uuid.uuid4()),
        "materia": payload.materia,
        "materia_id": payload.materia_id,
        "grupo": payload.grupo,
        "docente": payload.docente,
        "aula": payload.aula,
        "nivel_confianza": 1.0,
        "estado": "confirmed",
        "celda_origen": None,
        "texto_original": None,
        "horarios": [{
            "dia": payload.dia,
            "hora_inicio": payload.hora_inicio,
            "hora_fin": payload.hora_fin,
            "bloques_cantidad": bloques_cantidad,
        }],
    }

    def _add_to(celdas: List[Dict]):
        for cell in celdas:
            if cell.get("dia") == payload.dia and cell.get("hora_inicio") == payload.hora_inicio:
                cell.setdefault("bloques", []).append(new_block)
                return
        celdas.append({
            "dia": payload.dia,
            "hora_inicio": payload.hora_inicio,
            "hora_fin": payload.hora_fin,
            "bloques": [new_block],
            "celda_ref": None,
        })

    # MONGODB-READY: Reemplazado por storage.update()
    # NOTA: do_create NO debe ser async porque storage.update() llama a update_fn sin await
    def do_create(schedule: Dict) -> None:
        hojas_data = schedule.get("hojas_data") or {}
        if payload.sheet not in hojas_data:
            raise HTTPException(status_code=404, detail=f"Hoja '{payload.sheet}' no encontrada")
        
        _add_to(hojas_data[payload.sheet].setdefault("celdas", []))
        if schedule.get("hoja_actual") == payload.sheet:
            _add_to(schedule.setdefault("celdas", []))
    
    success = await storage.update(schedule_id, do_create)
    if not success:
        raise HTTPException(status_code=404, detail="Horario no encontrado")

    return {"message": "Bloque creado exitosamente", "block": new_block}

@api_router.patch("/schedule/{schedule_id}/blocks/bulk")
async def bulk_update_blocks(schedule_id: str, payload: BulkBlockUpdate):
    """Actualiza múltiples bloques con los mismos campos. Solo se aplican campos no nulos."""
    update = payload.update
    not_found = []
    updated_ids = set()
    
    def do_bulk_update(schedule: Dict) -> None:
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
    
    # MONGODB-READY: Reemplazado por storage.update()
    success = await storage.update(schedule_id, do_bulk_update)
    if not success:
        raise HTTPException(status_code=404, detail="Horario no encontrado")

    return {
        "message": f"{len(updated_ids)} bloque(s) actualizado(s)",
        "updated": list(updated_ids),
        "not_found": not_found,
    }

@api_router.delete("/schedule/{schedule_id}/blocks/bulk")
async def bulk_delete_blocks(schedule_id: str, payload: dict):
    """Elimina múltiples bloques en una sola operación atómica."""
    block_ids = payload.get("block_ids", [])
    deleted_ids = []
    not_found = []

    def do_bulk_delete(schedule: Dict) -> None:
        for block_id in block_ids:
            count = _delete_block_from_schedule(schedule, block_id)
            if count > 0:
                deleted_ids.append(block_id)
            else:
                not_found.append(block_id)

    success = await storage.update(schedule_id, do_bulk_delete)
    if not success:
        raise HTTPException(status_code=404, detail="Horario no encontrado")

    return {
        "message": f"{len(deleted_ids)} bloque(s) eliminado(s)",
        "deleted": deleted_ids,
        "not_found": not_found,
    }


@api_router.post("/schedule/{schedule_id}/export")
@limiter.limit("10/minute")
async def export_schedule(request: Request, schedule_id: str):
    """
    Exporta el horario al formato JSON especificado.
    
    Rate limit: 10 exportaciones por minuto por IP.
    """
    # MONGODB-READY: Reemplazado por storage.get()
    # schedule = await db.schedules.find_one({"id": schedule_id}, {"_id": 0})
    schedule = await storage.get(schedule_id)
    
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

    def do_update_horarios(schedule: Dict) -> None:
        matches = _find_block_locations(schedule, block_id)
        if not matches:
            raise HTTPException(status_code=404, detail="Bloque no encontrado")
        
        for _c, blk, _cl in matches:
            blk["horarios"] = horarios_procesados
    
    # MONGODB-READY: Reemplazado por storage.update()
    success = await storage.update(schedule_id, do_update_horarios)
    if not success:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    
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
    
    # MONGODB-READY: Reemplazado por storage.get()
    # schedule = await db.schedules.find_one({"id": schedule_id}, {"_id": 0})
    schedule = await storage.get(schedule_id)
    
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
    """Mueve un bloque a una nueva celda (drag & drop). Sincroniza en TODAS las
    colecciones donde el bloque exista (top-level + hojas_data) y actualiza horarios."""
    from utils.time_utils import calcular_bloques_horarios

    bloques_cant, _ = calcular_bloques_horarios(move.to_hora_inicio, move.to_hora_fin)
    new_horario = {
        "dia": move.to_dia,
        "hora_inicio": move.to_hora_inicio,
        "hora_fin": move.to_hora_fin,
        "bloques_cantidad": bloques_cant,
    }

    def do_move(schedule: Dict) -> None:
        # Localizar TODAS las copias del bloque
        matches = []  # list of (cell, block, celdas_list)
        for celdas in _iter_celdas_collections(schedule):
            for cell in celdas:
                if cell.get("dia") == move.from_dia and cell.get("hora_inicio") == move.from_hora_inicio:
                    for block in cell.get("bloques", []):
                        if block.get("id") == move.block_id:
                            matches.append((cell, block, celdas))
                            break

        if not matches:
            raise HTTPException(status_code=404, detail="Bloque no encontrado")

        for from_cell, block, target_celdas in matches:
            # Sincronizar horarios
            horarios = block.get("horarios") or []
            replaced = False
            for i, h in enumerate(horarios):
                if h.get("dia") == move.from_dia and h.get("hora_inicio") == move.from_hora_inicio:
                    horarios[i] = dict(new_horario)
                    replaced = True
                    break
            if not replaced:
                if horarios:
                    horarios[0] = dict(new_horario)
                else:
                    horarios = [dict(new_horario)]
            block["horarios"] = horarios

            # Quitar de from_cell
            from_cell["bloques"] = [b for b in from_cell["bloques"] if b["id"] != move.block_id]

            # Insertar en to_cell de la MISMA colección
            to_cell = None
            for cell in target_celdas:
                if cell.get("dia") == move.to_dia and cell.get("hora_inicio") == move.to_hora_inicio:
                    to_cell = cell
                    break
            if not to_cell:
                to_cell = {
                    "dia": move.to_dia,
                    "hora_inicio": move.to_hora_inicio,
                    "hora_fin": move.to_hora_fin,
                    "bloques": [],
                    "celda_ref": None,
                }
                target_celdas.append(to_cell)
            to_cell["bloques"].append(block)
    
    # MONGODB-READY: Reemplazado por storage.update()
    success = await storage.update(schedule_id, do_move)
    if not success:
        raise HTTPException(status_code=404, detail="Horario no encontrado")

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
@limiter.limit("30/minute")
async def search_subjects(request: Request, query: str, program_id: str = "ingenieria_de_sistemas", limit: int = 10):
    """
    Busca materias por texto con fuzzy matching en un programa específico.
    
    Rate limit: 30 búsquedas por minuto por IP.
    """
    # Limitar longitud de query para evitar abuso
    if len(query) > 100:
        raise HTTPException(status_code=400, detail="Query demasiado largo (máx 100 caracteres)")
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

logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_event():
    """Inicializa recursos que requieren event loop."""
    # Iniciar tarea de limpieza TTL del storage
    storage.start_cleanup()
    logger.info("Storage cleanup task iniciado")

@app.on_event("shutdown")
async def shutdown_db_client():
    # MONGODB-READY: Cierre de MongoDB preservado
    # client.close()
    
    # Cerrar storage (libera recursos de caché y cancela tareas TTL)
    await storage.close()
    logger.info("Storage cerrado correctamente")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
