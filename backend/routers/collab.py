from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import logging
from utils.collab_manager import manager
from utils.auth_helper import decode_access_token

router = APIRouter(tags=["Collaboration"])
logger = logging.getLogger(__name__)

@router.websocket("/ws/collab/{schedule_id}")
async def collab_endpoint(websocket: WebSocket, schedule_id: str, token: str = Query(...)):
    await websocket.accept()
    
    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        await websocket.close(code=4003, reason="Token inválido o expirado")
        return
        
    username = payload.get("sub")
    await manager.connect(schedule_id, username, websocket)
    logger.info(f"WebSocket connected: {username} on {schedule_id}")
    
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
                sheet = data.get("sheet")
                if sheet:
                    async with manager._mutex:
                        if schedule_id in manager.locks and sheet in manager.locks[schedule_id]:
                            del manager.locks[schedule_id][sheet]
                    locks = await manager.get_locks(schedule_id)
                    await manager.broadcast(schedule_id, {
                        "action": "LOCK_STATUS_UPDATE",
                        "locks": locks
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
        freed_sheets = await manager.disconnect(schedule_id, username)
        
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
