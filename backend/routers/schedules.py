from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from typing import Dict, List, Any, Optional
from models import BlockUpdate, BulkBlockUpdate, BlockCreate, BlockMove
from state import limiter, programas_dict
from storage import storage
import uuid
import os
import tempfile
import logging
import openpyxl
import asyncio
from collections import defaultdict
from utils.schedule_helpers import (
    _atomic_update_with_retry,
    _add_audit_log,
    _iter_celdas_collections,
    _update_block_in_schedule,
    _delete_block_from_schedule,
    _find_block_locations
)
from utils.export_helper import export_to_json_format
from utils.excel_html_renderer import sheet_to_html

router = APIRouter(tags=["Schedules"])

# In-memory cache: schedule_id → temp file path with original Excel bytes
_excel_file_cache: Dict[str, str] = {}
_excel_locks = defaultdict(asyncio.Lock)


def register_excel_file(schedule_id: str, file_path: str):
    """Registra la ruta del archivo Excel original asociado a un schedule.
    Llamado desde upload.py después de procesar el archivo."""
    _excel_file_cache[schedule_id] = file_path



@router.get("/schedules")
async def get_schedules():
    """Lista todos los horarios procesados"""
    # MONGODB-READY: Reemplazado por storage.list_all()
    # schedules = await db.schedules.find({}, {"_id": 0}).to_list(1000)
    schedules = await storage.list_all(1000)
    return schedules

@router.get("/schedule/{schedule_id}")
async def get_schedule(schedule_id: str):
    """Obtiene un horario específico con todos sus detalles"""
    # MONGODB-READY: Reemplazado por storage.get()
    # schedule = await db.schedules.find_one({"id": schedule_id}, {"_id": 0})
    schedule = await storage.get(schedule_id)
    
    if not schedule:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    
    return schedule


@router.get("/schedule/{schedule_id}/sheet-preview/{sheet_name}")
async def get_sheet_preview(
    schedule_id: str,
    sheet_name: str,
    highlight: Optional[str] = None,
):
    """Devuelve el HTML estilizado de una hoja del Excel original.

    - `sheet_name`: nombre de la hoja (URL-encoded si tiene espacios).
    - `highlight`: referencia de celda a resaltar, ej. 'B5'. Opcional.

    El HTML resultante se renderiza directamente con dangerouslySetInnerHTML
    en el frontend dentro de un panel con zoom independiente.
    """
    # 1. Verificar que el horario existe
    schedule = await storage.get(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Horario no encontrado")

    # 2. Buscar el archivo Excel en caché
    excel_path = _excel_file_cache.get(schedule_id)
    if not excel_path or not os.path.exists(excel_path):
        raise HTTPException(
            status_code=404,
            detail="El archivo Excel original no está disponible. "
                   "Esto ocurre si el servidor fue reiniciado después de la subida."
        )

    # 3. Abrir y renderizar
    try:
        async with _excel_locks[schedule_id]:
            def _render():
                wb = openpyxl.load_workbook(excel_path, data_only=True, read_only=False)
                html_c = sheet_to_html(wb, sheet_name, highlight_ref=highlight)
                wb.close()
                return html_c
            html_content = await asyncio.to_thread(_render)
    except Exception as e:
        logging.error(f"Error generando preview HTML para {schedule_id}/{sheet_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generando vista previa: {str(e)}")

    return HTMLResponse(content=html_content, media_type="text/html; charset=utf-8")


@router.put("/schedule/{schedule_id}/cell/{dia}/{hora_inicio}/block/{block_id}")
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
        
        _add_audit_log(schedule, "ACTUALIZAR_BLOQUE", block_id, f"Se actualizó materia, grupo, docente o aula")
        
        return schedule, result
    
    return await _atomic_update_with_retry(schedule_id, do_update)


@router.delete("/schedule/{schedule_id}/cell/{dia}/{hora_inicio}/block/{block_id}")
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
        
        _add_audit_log(schedule, "ELIMINAR_BLOQUE", block_id, f"Bloque eliminado de {deleted_count} ubicaciones")
        
        return schedule, result
    
    return await _atomic_update_with_retry(schedule_id, do_delete)

@router.post("/schedule/{schedule_id}/block")
async def create_block(schedule_id: str, payload: BlockCreate):
    """Crea un nuevo bloque en la celda indicada (día/hora) de una hoja específica.

    Si la celda aún no existe, se crea. Si la hoja indicada es `hoja_actual`, también
    se sincroniza con el array top-level `celdas`.
    """
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
            
        _add_audit_log(schedule, "CREAR_BLOQUE", new_block["id"], f"Nuevo bloque creado: {payload.materia}")
    
    success = await storage.update(schedule_id, do_create)
    if not success:
        raise HTTPException(status_code=404, detail="Horario no encontrado")

    return {"message": "Bloque creado exitosamente", "block": new_block}

@router.patch("/schedule/{schedule_id}/blocks/bulk")
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
            _add_audit_log(schedule, "ACTUALIZACION_MASIVA", block_id, "Actualización desde operación masiva")
    
    # MONGODB-READY: Reemplazado por storage.update()
    success = await storage.update(schedule_id, do_bulk_update)
    if not success:
        raise HTTPException(status_code=404, detail="Horario no encontrado")

    return {
        "message": f"{len(updated_ids)} bloque(s) actualizado(s)",
        "updated": list(updated_ids),
        "not_found": not_found,
    }

@router.delete("/schedule/{schedule_id}/blocks/bulk")
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
                _add_audit_log(schedule, "ELIMINACION_MASIVA", block_id, "Eliminado desde operación masiva")
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


@router.put("/schedule/{schedule_id}/state")
async def update_schedule_state(schedule_id: str, request: Request):
    """Sobrescribe el estado completo del horario (usado para deshacer/rehacer)"""
    new_data = await request.json()
    def do_overwrite(schedule: Dict) -> None:
        schedule.clear()
        schedule.update(new_data)
        _add_audit_log(schedule, "RESTAURAR_ESTADO", None, "Estado sobrescrito completo (Deshacer/Rehacer)")
    success = await storage.update(schedule_id, do_overwrite)
    if not success:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    return {"message": "Estado restaurado"}

@router.post("/schedule/{schedule_id}/export")
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


@router.post("/schedule/{schedule_id}/publish")
@limiter.limit("5/minute")
async def publish_schedule(request: Request, schedule_id: str):
    """
    Exporta el horario y lo publica automáticamente en Cloudflare R2.

    Body JSON requerido:
        semester (str): Identificador del semestre, ej. "2026-1".
        filename (str): Nombre base del archivo, ej. "ingenieria_de_sistemas".
                        No incluir extensión .json; se agrega automáticamente.

    Respuesta exitosa:
        success  (bool): true
        url      (str):  URL pública del archivo en R2.
        semester (str):  Semestre utilizado.
        filename (str):  Nombre de archivo sanitizado con extensión.

    Rate limit: 5 publicaciones por minuto por IP.
    """
    from utils.r2_uploader import upload_schedule_json, is_r2_configured

    # Verificar configuración de R2 antes de procesar nada
    if not is_r2_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Cloudflare R2 no está configurado. "
                "Añade las variables R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, "
                "R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME y R2_PUBLIC_URL "
                "en el archivo backend/.env."
            ),
        )

    body = await request.json()
    semester = (body.get("semester") or "").strip()
    filename = (body.get("filename") or "").strip()

    if not semester:
        raise HTTPException(status_code=400, detail="El campo 'semester' es requerido (ej. '2026-1').")
    if not filename:
        raise HTTPException(status_code=400, detail="El campo 'filename' es requerido (ej. 'ingenieria_de_sistemas').")

    # MONGODB-READY: Reemplazado por storage.get()
    schedule = await storage.get(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Horario no encontrado")

    program_id = schedule.get("programa_id", "ingenieria_de_sistemas")
    subject_dict = programas_dict.get(program_id, {}).get("diccionario", {})
    exported = export_to_json_format(schedule, subject_dict)

    try:
        public_url = await asyncio.to_thread(
            upload_schedule_json,
            semester,
            filename,
            exported,
            program_id,
            schedule.get("programa_nombre", ""),
        )
    except Exception as e:
        logging.error(f"Error al publicar en R2 (schedule={schedule_id}): {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error al publicar en Cloudflare R2: {str(e)}",
        )

    return JSONResponse(content={
        "success": True,
        "url": public_url,
        "semester": semester,
        "filename": filename if filename.endswith(".json") else f"{filename}.json",
    })

@router.put("/schedule/{schedule_id}/block/{block_id}/horarios")
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
            
        _add_audit_log(schedule, "ACTUALIZAR_HORARIOS", block_id, f"Horarios actualizados a {len(horarios_procesados)} slots")
    
    # MONGODB-READY: Reemplazado por storage.update()
    success = await storage.update(schedule_id, do_update_horarios)
    if not success:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    
    return {
        "message": "Horarios actualizados exitosamente",
        "block_id": block_id,
        "horarios": horarios_procesados
    }

@router.get("/schedule/{schedule_id}/search")
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

@router.post("/schedule/{schedule_id}/move-block")
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
            
        _add_audit_log(schedule, "MOVER_BLOQUE", move.block_id, f"Movido de {move.from_dia} {move.from_hora_inicio} a {move.to_dia} {move.to_hora_inicio}")
    
    # MONGODB-READY: Reemplazado por storage.update()
    success = await storage.update(schedule_id, do_move)
    if not success:
        raise HTTPException(status_code=404, detail="Horario no encontrado")

    return {"message": "Bloque movido exitosamente", "block_id": move.block_id}

