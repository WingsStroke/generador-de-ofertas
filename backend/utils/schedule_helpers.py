from typing import List, Dict
from datetime import datetime, timezone
from fastapi import HTTPException
from models import BlockUpdate
from storage import storage

async def _atomic_update_with_retry(
    schedule_id: str,
    update_fn,
    max_retries: int = 3,
    backoff_ms: float = 50.0
) -> Dict:
    def wrapped_update_fn(data: Dict) -> None:
        nonlocal result_data
        _updated_data, result_data = update_fn(data)
    
    result_data = None
    success = await storage.update(schedule_id, wrapped_update_fn)
    
    if not success:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    
    return result_data

def _add_audit_log(schedule: Dict, accion: str, bloque_id: str = None, detalles: str = ""):
    if "historial_cambios" not in schedule:
        schedule["historial_cambios"] = []
    
    schedule["historial_cambios"].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "accion": accion,
        "bloque_id": bloque_id,
        "detalles": detalles
    })

def _iter_celdas_collections(schedule: Dict) -> List[List[Dict]]:
    collections = []
    if schedule.get("celdas"):
        collections.append(schedule["celdas"])
    hojas_data = schedule.get("hojas_data") or {}
    for hoja_info in hojas_data.values():
        if isinstance(hoja_info, dict) and hoja_info.get("celdas"):
            collections.append(hoja_info["celdas"])
    return collections

def _find_block_locations(schedule: Dict, block_id: str):
    matches = []
    for celdas in _iter_celdas_collections(schedule):
        for cell in celdas:
            for block in cell.get("bloques", []):
                if block.get("id") == block_id:
                    matches.append((cell, block, celdas))
    return matches

def _update_block_in_schedule(schedule: Dict, block_id: str, update: BlockUpdate) -> int:
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
        blk["_updated_at"] = datetime.now(timezone.utc).isoformat()
        updated_count += 1
    return updated_count

def _delete_block_from_schedule(schedule: Dict, block_id: str) -> int:
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
