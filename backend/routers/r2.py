from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import uuid
import logging
from datetime import datetime, timezone

from database import db_instance
from state import programas_dict
from storage import storage
from routers.auth import get_current_admin
from utils.r2_uploader import get_r2_index, get_r2_object, is_r2_configured
from utils.import_json_helper import validate_import_json_structure, build_schedule_from_import_json

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Cloudflare R2 Editor"])

class R2ImportRequest(BaseModel):
    semester: str
    filename: str

@router.get("/r2/schedules")
async def list_r2_schedules(admin: dict = Depends(get_current_admin)):
    """
    Obtiene la lista de ofertas académicas publicadas en Cloudflare R2.
    Solo accesible para el rol 'admin'.
    """
    if not is_r2_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cloudflare R2 no está configurado en el servidor."
        )
    try:
        index_data = get_r2_index()
        return index_data
    except Exception as e:
        logger.error(f"Error listando horarios en R2: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al conectar con Cloudflare R2: {str(e)}"
        )

@router.post("/r2/import")
async def import_r2_schedule(req: R2ImportRequest, admin: dict = Depends(get_current_admin)):
    """
    Descarga una oferta académica desde R2 y la guarda localmente en MongoDB.
    Solo accesible para el rol 'admin'.
    """
    if not is_r2_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cloudflare R2 no está configurado en el servidor."
        )
    
    # 1. Descargar el JSON desde R2
    try:
        data = get_r2_object(req.semester, req.filename)
    except Exception as e:
        logger.error(f"Error descargando {req.semester}/{req.filename} desde R2: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró el archivo en R2 o falló la conexión: {str(e)}"
        )
        
    # 2. Validar estructura básica del JSON
    errors = validate_import_json_structure(data)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "El JSON descargado de R2 no tiene la estructura de oferta académica válida.",
                "errors": errors,
            },
        )
        
    # 3. Procesar y convertir a formato MongoDB (reutilizando lógica de import-json)
    try:
        schedule_dict, import_meta = build_schedule_from_import_json(
            data,
            programas_dict,
            default_filename=req.filename,
        )

        await storage.create(schedule_dict)

        return {
            "schedule_id": import_meta["schedule_id"],
            "message": "Oferta descargada e importada desde R2 exitosamente",
            "programa": import_meta["programa"],
            "semester": req.semester,
            "filename": req.filename
        }

    except Exception as e:
        logger.error(f"Error procesando JSON de R2: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno al procesar e importar la oferta: {str(e)}"
        )
