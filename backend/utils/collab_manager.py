import asyncio
from typing import Dict, List, Any
from fastapi import WebSocket

class CollaborationManager:
    def __init__(self):
        # Dict[schedule_id, Dict[username, WebSocket]]
        self.active_sessions: Dict[str, Dict[str, WebSocket]] = {}
        
        # Dict[schedule_id, Dict[sheet_name, username]]
        self.locks: Dict[str, Dict[str, str]] = {}
        
        # A global asyncio lock to avoid race conditions when modifying internal state
        self._mutex = asyncio.Lock()

    async def connect(self, schedule_id: str, username: str, websocket: WebSocket):
        async with self._mutex:
            if schedule_id not in self.active_sessions:
                self.active_sessions[schedule_id] = {}
                self.locks[schedule_id] = {}
                
            # If the user already had a connection, close the old one
            if username in self.active_sessions[schedule_id]:
                old_ws = self.active_sessions[schedule_id][username]
                try:
                    await old_ws.send_json({"action": "error", "message": "Conectado desde otra pestaña."})
                    await old_ws.close()
                except Exception:
                    pass
                    
            self.active_sessions[schedule_id][username] = websocket
            
    async def disconnect(self, schedule_id: str, username: str):
        async with self._mutex:
            locks_to_free = []
            if schedule_id in self.active_sessions:
                if username in self.active_sessions[schedule_id]:
                    del self.active_sessions[schedule_id][username]
                
                # Free locks held by this user
                if schedule_id in self.locks:
                    for sheet, owner in list(self.locks[schedule_id].items()):
                        if owner == username:
                            del self.locks[schedule_id][sheet]
                            locks_to_free.append(sheet)
                
                # Cleanup empty sessions to prevent memory leaks
                if not self.active_sessions[schedule_id]:
                    del self.active_sessions[schedule_id]
                    if schedule_id in self.locks:
                        del self.locks[schedule_id]
                        
            return locks_to_free

    async def broadcast(self, schedule_id: str, message: dict, exclude: str = None):
        if schedule_id not in self.active_sessions:
            return
            
        disconnected_users = []
        # Clone the dict to avoid RuntimeError if changed during iteration
        connections = dict(self.active_sessions[schedule_id])
        
        for username, ws in connections.items():
            if exclude and username == exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                disconnected_users.append(username)
                
        # Clean up any that failed
        for user in disconnected_users:
            await self.disconnect(schedule_id, user)

    async def get_presence(self, schedule_id: str) -> List[str]:
        if schedule_id not in self.active_sessions:
            return []
        return list(self.active_sessions[schedule_id].keys())
        
    async def get_locks(self, schedule_id: str) -> Dict[str, str]:
        if schedule_id not in self.locks:
            return {}
        return dict(self.locks[schedule_id])
        
    async def acquire_lock(self, schedule_id: str, sheet_name: str, username: str) -> bool:
        async with self._mutex:
            if schedule_id not in self.locks:
                return False
                
            current_owner = self.locks[schedule_id].get(sheet_name)
            if current_owner is None or current_owner == username:
                # Assign the lock
                self.locks[schedule_id][sheet_name] = username
                return True
            else:
                return False

    async def release_lock(self, schedule_id: str, sheet_name: str, username: str) -> bool:
        async with self._mutex:
            if schedule_id in self.locks:
                current_owner = self.locks[schedule_id].get(sheet_name)
                if current_owner == username:
                    del self.locks[schedule_id][sheet_name]
                    return True
                # Allow admin override (for future Fase 3)
                if username.startswith("Admin-"):
                    del self.locks[schedule_id][sheet_name]
                    return True
            return False

# Singleton instance
manager = CollaborationManager()
