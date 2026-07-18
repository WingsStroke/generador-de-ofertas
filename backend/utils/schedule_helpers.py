from typing import List, Dict
from datetime import datetime, timezone
import asyncio
from fastapi import HTTPException
from models import BlockUpdate
from storage import storage
from utils.subject_resolver import resolve_subject_fields

async def _atomic_update_with_retry(
    schedule_id: str,
    update_fn,
    max_retries: int = 3,
    backoff_ms: float = 50.0
) -> Dict:
    class _RetryConflict(Exception):
        pass

    for attempt in range(max_retries):
        current = await storage.get(schedule_id)
        if not current:
            raise HTTPException(status_code=404, detail="Horario no encontrado")

        expected_v = current.get("_v", 0)
        result_data = None

        def wrapped_update_fn(data: Dict) -> None:
            nonlocal result_data
            current_v = data.get("_v", 0)
            if current_v != expected_v:
                raise _RetryConflict()
            _updated_data, result_data = update_fn(data)

        try:
            success = await storage.update(schedule_id, wrapped_update_fn)
        except _RetryConflict:
            if attempt == max_retries - 1:
                raise HTTPException(
                    status_code=409,
                    detail="Conflicto de concurrencia al actualizar el horario. Intenta nuevamente.",
                )
            await asyncio.sleep((backoff_ms / 1000.0) * (attempt + 1))
            continue

        if not success:
            raise HTTPException(status_code=404, detail="Horario no encontrado")

        return result_data

    raise HTTPException(
        status_code=409,
        detail="No fue posible completar la actualización por conflictos de concurrencia.",
    )

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
        if update.materia is not None or update.materia_id is not None or update.codigo is not None or update.creditos is not None:
            materia_in = update.materia if update.materia is not None else blk.get("materia")
            materia_id_in = update.materia_id if update.materia_id is not None else blk.get("materia_id")
            codigo_in = update.codigo if update.codigo is not None else blk.get("codigo")
            creditos_in = update.creditos if update.creditos is not None else blk.get("creditos")

            resolved = resolve_subject_fields(
                program_id=schedule.get("programa_id", "ingenieria_de_sistemas"),
                materia=materia_in,
                materia_id=materia_id_in,
                codigo=codigo_in,
                creditos=creditos_in,
            )
            blk["materia"] = resolved["nombre"]
            blk["materia_id"] = resolved["id"]
            blk["codigo"] = resolved.get("codigo")
            blk["creditos"] = resolved.get("creditos")

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
