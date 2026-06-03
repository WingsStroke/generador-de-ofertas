from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from typing import Dict, List, Any, Optional
from models import BlockUpdate, BulkBlockUpdate, BlockCreate, BlockMove, GlobalReplaceRequest
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


@router.post("/schedule/{schedule_id}/replace")
async def global_replace(schedule_id: str, request: GlobalReplaceRequest):
    """Busca y reemplaza ocurrencias de un texto en todo el horario (o en la hoja actual)"""
    import re
    from datetime import datetime, timezone
    
    schedule = await storage.get(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
        
    replaced_count = [0]  # list wrapper so nested function can mutate
    sheets_affected = set()
    
    def get_replaced_value(val: str) -> tuple[str, bool]:
        if not val or not isinstance(val, str):
            return val, False
        
        is_match = False
        if request.exact_match:
            if request.case_sensitive:
                is_match = (val == request.search_text)
            else:
                is_match = (val.lower() == request.search_text.lower())
        else:
            if request.case_sensitive:
                is_match = (request.search_text in val)
            else:
                is_match = (request.search_text.lower() in val.lower())
                
        if not is_match:
            return val, False
            
        if request.exact_match:
            return request.replace_text, True
        else:
            if request.case_sensitive:
                return val.replace(request.search_text, request.replace_text), True
            else:
                pattern = re.compile(re.escape(request.search_text), re.IGNORECASE)
                new_val = pattern.sub(request.replace_text, val)
                return new_val, True

    def do_replace(sched: Dict) -> tuple:
        hojas_data = sched.get("hojas_data", {})
        if not hojas_data:
            hoja_actual = sched.get("hoja_actual", "Hoja 1")
            hojas_data = {hoja_actual: {"celdas": sched.get("celdas", [])}}
            sched["hojas_data"] = hojas_data
            
        for sheet_name, sheet_info in hojas_data.items():
            if request.scope == "current" and request.current_sheet and sheet_name != request.current_sheet:
                continue
                
            sheet_affected = False
            for cell in sheet_info.get("celdas", []):
                for block in cell.get("bloques", []):
                    fields_to_check = []
                    if request.field == "all":
                        fields_to_check = ["materia", "docente", "aula"]
                    else:
                        fields_to_check = [request.field]
                        
                    block_updated = False
                    for f in fields_to_check:
                        old_val = block.get(f)
                        if old_val:
                            new_val, changed = get_replaced_value(old_val)
                            if changed:
                                block[f] = new_val
                                block_updated = True
                                replaced_count[0] += 1
                    
                    if block_updated:
                        block["estado"] = "confirmed"
                        block["nivel_confianza"] = 1.0
                        block["_updated_at"] = datetime.now(timezone.utc).isoformat()
                        sheet_affected = True
                        
            if sheet_affected:
                sheets_affected.add(sheet_name)
                
        # Sincronizar schedule["celdas"] si la hoja activa es una de las afectadas
        hoja_actual = sched.get("hoja_actual")
        if hoja_actual and hoja_actual in sheets_affected:
            for cell in sched.get("celdas", []):
                for block in cell.get("bloques", []):
                    fields_to_check = []
                    if request.field == "all":
                        fields_to_check = ["materia", "docente", "aula"]
                    else:
                        fields_to_check = [request.field]
                    for f in fields_to_check:
                        old_val = block.get(f)
                        if old_val:
                            new_val, changed = get_replaced_value(old_val)
                            if changed:
                                block[f] = new_val
                                block["estado"] = "confirmed"
                                block["nivel_confianza"] = 1.0
                                block["_updated_at"] = datetime.now(timezone.utc).isoformat()
                                
        _add_audit_log(
            sched, 
            "REEMPLAZO_GLOBAL", 
            None, 
            f"Reemplazo global de '{request.search_text}' por '{request.replace_text}' en '{request.field}'. "
            f"Afecto {len(sheets_affected)} hoja(s) y {replaced_count[0]} bloque(s)."
        )
        return sched, {
            "message": "Reemplazo completado exitosamente",
            "replaced_count": replaced_count[0],
            "sheets_affected": list(sheets_affected)
        }

    return await _atomic_update_with_retry(schedule_id, do_replace)


@router.get("/schedule/{schedule_id}/lint")
async def lint_schedule(schedule_id: str):
    """Analiza el horario en busca de traslapes y datos faltantes"""
    schedule = await storage.get(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
        
    occurrences = []
    hojas_data = schedule.get("hojas_data", {})
    if not hojas_data:
        hoja_actual = schedule.get("hoja_actual", "Hoja 1")
        hojas_data = {hoja_actual: {"celdas": schedule.get("celdas", [])}}
        
    for sheet_name, sheet_info in hojas_data.items():
        for cell in sheet_info.get("celdas", []):
            dia = cell.get("dia")
            hora_inicio = cell.get("hora_inicio")
            hora_fin = cell.get("hora_fin")
            if not dia or not hora_inicio or not hora_fin:
                continue
            for block in cell.get("bloques", []):
                occurrences.append({
                    "sheet": sheet_name,
                    "dia": dia,
                    "hora_inicio": hora_inicio,
                    "hora_fin": hora_fin,
                    "block_id": block.get("id"),
                    "materia": block.get("materia", ""),
                    "grupo": block.get("grupo", ""),
                    "docente": block.get("docente", ""),
                    "aula": block.get("aula", ""),
                })
                
    errors = []
    warnings = []
    
    # helper for range overlap
    def ranges_overlap(start1: str, end1: str, start2: str, end2: str) -> bool:
        return max(start1, start2) < min(end1, end2)
        
    # 1. Check for missing data (Warnings)
    for occ in occurrences:
        materia = occ["materia"]
        grupo = occ["grupo"]
        docente = occ["docente"]
        aula = occ["aula"]
        sheet = occ["sheet"]
        dia = occ["dia"]
        hora_inicio = occ["hora_inicio"]
        hora_fin = occ["hora_fin"]
        block_id = occ["block_id"]
        
        dia_label = {"L": "Lunes", "M": "Martes", "X": "Miércoles", "J": "Jueves", "V": "Viernes", "S": "Sábado", "D": "Domingo"}.get(dia, dia)
        
        if not materia or not materia.strip():
            warnings.append({
                "id": f"missing_materia_{block_id}",
                "type": "missing_materia",
                "message": f"Falta el nombre de la materia ({dia_label} {hora_inicio}-{hora_fin})",
                "sheet": sheet,
                "dia": dia,
                "hora_inicio": hora_inicio,
                "block_id": block_id
            })
        if not docente or not docente.strip() or docente.lower() in ["por designar", "sin asignar", "vacante", "a convenir"]:
            warnings.append({
                "id": f"missing_docente_{block_id}",
                "type": "missing_docente",
                "message": f"Falta el docente para '{materia or '(Sin materia)'}' - Grupo {grupo or '(Sin grupo)'} ({dia_label} {hora_inicio}-{hora_fin})",
                "sheet": sheet,
                "dia": dia,
                "hora_inicio": hora_inicio,
                "block_id": block_id
            })
        if not aula or not aula.strip() or aula.lower() in ["por asignar", "sin asignar"]:
            warnings.append({
                "id": f"missing_aula_{block_id}",
                "type": "missing_aula",
                "message": f"Falta el aula para '{materia or '(Sin materia)'}' - Grupo {grupo or '(Sin grupo)'} ({dia_label} {hora_inicio}-{hora_fin})",
                "sheet": sheet,
                "dia": dia,
                "hora_inicio": hora_inicio,
                "block_id": block_id
            })
        if not grupo or not grupo.strip():
            warnings.append({
                "id": f"missing_grupo_{block_id}",
                "type": "missing_grupo",
                "message": f"Falta el grupo para '{materia or '(Sin materia)'}' ({dia_label} {hora_inicio}-{hora_fin})",
                "sheet": sheet,
                "dia": dia,
                "hora_inicio": hora_inicio,
                "block_id": block_id
            })
            
    # 2. Check for overlaps (Errors)
    n = len(occurrences)
    for i in range(n):
        for j in range(i + 1, n):
            o1 = occurrences[i]
            o2 = occurrences[j]
            
            if o1["dia"] == o2["dia"] and ranges_overlap(o1["hora_inicio"], o1["hora_fin"], o2["hora_inicio"], o2["hora_fin"]):
                dia_label = {"L": "Lunes", "M": "Martes", "X": "Miércoles", "J": "Jueves", "V": "Viernes", "S": "Sábado", "D": "Domingo"}.get(o1["dia"], o1["dia"])
                
                # Check teacher overlap
                d1 = o1["docente"].strip() if o1["docente"] else ""
                d2 = o2["docente"].strip() if o2["docente"] else ""
                if d1 and d2 and d1.lower() == d2.lower() and d1.lower() not in ["por designar", "sin asignar", "vacante", "a convenir"]:
                    errors.append({
                        "id": f"conflict_docente_{o1['block_id']}_{o2['block_id']}",
                        "type": "docente_overlap",
                        "message": f"Traslape de docente '{o1['docente']}': '{o1['materia']}' en '{o1['sheet']}' ({dia_label} {o1['hora_inicio']}-{o1['hora_fin']}) y '{o2['materia']}' en '{o2['sheet']}' ({dia_label} {o2['hora_inicio']}-{o2['hora_fin']})",
                        "sheet": o1["sheet"],
                        "dia": o1["dia"],
                        "hora_inicio": o1["hora_inicio"],
                        "block_id": o1["block_id"],
                        "related_sheet": o2["sheet"],
                        "related_block_id": o2["block_id"]
                    })
                    
                # Check classroom overlap
                a1 = o1["aula"].strip() if o1["aula"] else ""
                a2 = o2["aula"].strip() if o2["aula"] else ""
                if a1 and a2 and a1.lower() == a2.lower() and a1.lower() not in ["por asignar", "sin asignar"]:
                    errors.append({
                        "id": f"conflict_aula_{o1['block_id']}_{o2['block_id']}",
                        "type": "aula_overlap",
                        "message": f"Traslape de aula '{o1['aula']}': '{o1['materia']}' en '{o1['sheet']}' ({dia_label} {o1['hora_inicio']}-{o1['hora_fin']}) y '{o2['materia']}' en '{o2['sheet']}' ({dia_label} {o2['hora_inicio']}-{o2['hora_fin']})",
                        "sheet": o1["sheet"],
                        "dia": o1["dia"],
                        "hora_inicio": o1["hora_inicio"],
                        "block_id": o1["block_id"],
                        "related_sheet": o2["sheet"],
                        "related_block_id": o2["block_id"]
                    })
                    
                # Check group overlap within same sheet
                if o1["sheet"] == o2["sheet"]:
                    g1 = o1["grupo"].strip() if o1["grupo"] else ""
                    g2 = o2["grupo"].strip() if o2["grupo"] else ""
                    if g1 and g2 and g1.lower() == g2.lower():
                        errors.append({
                            "id": f"conflict_grupo_{o1['block_id']}_{o2['block_id']}",
                            "type": "grupo_overlap",
                            "message": f"Traslape de grupo '{o1['grupo']}': '{o1['materia']}' ({dia_label} {o1['hora_inicio']}-{o1['hora_fin']}) y '{o2['materia']}' ({dia_label} {o2['hora_inicio']}-{o2['hora_fin']})",
                            "sheet": o1["sheet"],
                            "dia": o1["dia"],
                            "hora_inicio": o1["hora_inicio"],
                            "block_id": o1["block_id"],
                            "related_sheet": o2["sheet"],
                            "related_block_id": o2["block_id"]
                        })
                        
    return {
        "errors": errors,
        "warnings": warnings,
        "total_errors": len(errors),
        "total_warnings": len(warnings)
    }



