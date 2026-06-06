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
    if "metadata" not in data or "semestres" not in data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El JSON descargado de R2 no tiene la estructura de oferta académica válida."
        )
        
    # 3. Procesar y convertir a formato MongoDB (reutilizando lógica de import-json)
    try:
        meta = data.get("metadata", {})
        programa_nombre = meta.get("programa", "Programa importado de R2")
        nombre_archivo = meta.get("archivo", req.filename)
        fecha = meta.get("fechaProcesamiento", datetime.now(timezone.utc).isoformat())

        # Intentar inferir programa_id
        programa_id = "ingenieria_de_sistemas"
        for pid, pdata in programas_dict.items():
            if pdata["nombre"].lower() in programa_nombre.lower() or programa_nombre.lower() in pdata["nombre"].lower():
                programa_id = pid
                break

        preview_data = data.get("_raw_preview_data", {})
        hojas_data = {}

        for sem in data["semestres"]:
            num = sem.get("numero", 0)
            sheet_name = f"Table {num}" if num > 0 else "Table 1"
            celdas = []

            for asig in sem.get("asignaturas", []):
                materia_id = asig["id"]
                materia_nombre = asig["nombre"]
                creditos = asig.get("creditos")
                for grp in asig.get("grupos", []):
                    grupo_label = grp.get("grupo")
                    if not grupo_label or str(grupo_label).strip() == "N/A" or str(grupo_label).strip() == "":
                        grupo_label = None
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

            sheet_preview = preview_data.get(sheet_name, {})
            hojas_data[sheet_name] = {
                "nombre": sheet_name,
                "celdas": celdas,
                "estructura_dias": sheet_preview.get("estructura_dias", []),
                "estructura_horas": sheet_preview.get("estructura_horas", []),
                "excel_preview": sheet_preview.get("excel_preview", []),
                "nivel_confianza": 1.0,
            }

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
            "message": "Oferta descargada e importada desde R2 exitosamente",
            "programa": programa_nombre,
            "semester": req.semester,
            "filename": req.filename
        }

    except Exception as e:
        logger.error(f"Error procesando JSON de R2: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno al procesar e importar la oferta: {str(e)}"
        )
