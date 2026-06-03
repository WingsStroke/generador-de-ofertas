from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import logging
from utils.collab_manager import manager
from utils.auth_helper import decode_access_token
from storage import storage

router = APIRouter(tags=["Collaboration"])
logger = logging.getLogger(__name__)

@router.get("/collab/active")
async def get_active_sessions():
    """Retorna una lista de las sesiones colaborativas activas en este momento."""
    active_schedules = []
    
    # Iterate over a copy of the keys to avoid RuntimeError if dict changes
    for schedule_id in list(manager.active_sessions.keys()):
        presence = await manager.get_presence(schedule_id)
        if not presence:
            continue
            
        schedule = await storage.get(schedule_id)
        if schedule:
            active_schedules.append({
                "schedule_id": schedule_id,
                "nombre_archivo": schedule.get("nombre_archivo", "Desconocido"),
                "programa_nombre": schedule.get("programa_nombre", "Desconocido"),
                "fecha_procesamiento": schedule.get("fecha_procesamiento", ""),
                "usuarios_activos": presence
            })
            
    return active_schedules

@router.websocket("/ws/collab/{schedule_id}")
async def collab_endpoint(websocket: WebSocket, schedule_id: str, token: str = Query(...)):
    await websocket.accept()
    
    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        logger.warning(f"Token invalido: {token}")
        await websocket.close(code=4003, reason="Token inválido o expirado")
        return
        
    username = payload.get("sub")
    role = payload.get("role", "user")
    await manager.connect(schedule_id, username, websocket)
    logger.info(f"WebSocket connected: {username} ({role}) on {schedule_id}")
    
    # Broadcast current state to the new user and notify others of presence
    presence = await manager.get_presence(schedule_id)
    locks = await manager.get_locks(schedule_id)
    
    await websocket.send_json({
        "action": "INIT_STATE",
        "presence": presence,
        "locks": locks
    })
    
    await manager.broadcast(schedule_id, {
        "action": "PRESENCE_UPDATE",
        "presence": presence
    }, exclude=username)
    
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            
            if action == "ping":
                await websocket.send_json({"action": "pong"})
            elif action == "REQUEST_LOCK":
                sheet = data.get("sheet")
                if sheet:
                    granted = await manager.acquire_lock(schedule_id, sheet, username)
                    if granted:
                        await websocket.send_json({
                            "action": "LOCK_GRANTED",
                            "sheet": sheet
                        })
                        locks = await manager.get_locks(schedule_id)
                        await manager.broadcast(schedule_id, {
                            "action": "LOCK_STATUS_UPDATE",
                            "locks": locks
                        })
                    else:
                        await websocket.send_json({
                            "action": "LOCK_DENIED",
                            "sheet": sheet,
                            "reason": "Ya está en uso por otro usuario"
                        })
            elif action == "RELEASE_LOCK":
                sheet = data.get("sheet")
                if sheet:
                    released = await manager.release_lock(schedule_id, sheet, username)
                    if released:
                        locks = await manager.get_locks(schedule_id)
                        await manager.broadcast(schedule_id, {
                            "action": "LOCK_STATUS_UPDATE",
                            "locks": locks
                        })
            elif action == "FORCE_UNLOCK":
                if role != "admin":
                    await websocket.send_json({
                        "action": "ERROR",
                        "message": "No tienes permisos para forzar desbloqueo"
                    })
                    continue
                
                sheet = data.get("sheet")
                if sheet:
                    victim = None
                    async with manager._mutex:
                        if schedule_id in manager.locks and sheet in manager.locks[schedule_id]:
                            victim = manager.locks[schedule_id][sheet]
                            del manager.locks[schedule_id][sheet]
                    
                    if victim:
                        locks = await manager.get_locks(schedule_id)
                        await manager.broadcast(schedule_id, {
                            "action": "LOCK_STATUS_UPDATE",
                            "locks": locks
                        })
                        await manager.broadcast(schedule_id, {
                            "action": "FORCE_UNLOCKED",
                            "sheet": sheet,
                            "by": username,
                            "victim": victim
                        })
            elif action == "NOTIFY_UPDATE":
                sheet = data.get("sheet")
                if sheet:
                    # Broadcast DATA_CHANGED to everyone else
                    await manager.broadcast(schedule_id, {
                        "action": "DATA_CHANGED",
                        "sheet": sheet,
                        "by_user": username
                    }, exclude=username)
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected naturally: {username} on {schedule_id}")
    except Exception as e:
        logger.warning(f"WebSocket error for {username} on {schedule_id}: {str(e)}")
    finally:
        freed_sheets = await manager.disconnect(schedule_id, username, websocket)
        
        # Notify others that this user left
        presence = await manager.get_presence(schedule_id)
        if presence:
            await manager.broadcast(schedule_id, {
                "action": "PRESENCE_UPDATE",
                "presence": presence
            })
            
            # If the user held locks, notify others that they are free
            if freed_sheets:
                locks = await manager.get_locks(schedule_id)
                await manager.broadcast(schedule_id, {
                    "action": "LOCK_STATUS_UPDATE",
                    "locks": locks
                })
