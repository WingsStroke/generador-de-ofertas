import asyncio
from typing import Dict, List, Any
from fastapi import WebSocket

class CollaborationManager:
    def __init__(self):
        # Dict[schedule_id, Dict[username, List[WebSocket]]]
        self.active_sessions: Dict[str, Dict[str, List[WebSocket]]] = {}
        
        # Dict[schedule_id, Dict[sheet_name, username]]
        self.locks: Dict[str, Dict[str, str]] = {}
        
        # A global asyncio lock to avoid race conditions when modifying internal state
        self._mutex = asyncio.Lock()

    async def connect(self, schedule_id: str, username: str, websocket: WebSocket):
        async with self._mutex:
            if schedule_id not in self.active_sessions:
                self.active_sessions[schedule_id] = {}
                self.locks[schedule_id] = {}
                
            if username not in self.active_sessions[schedule_id]:
                self.active_sessions[schedule_id][username] = []
                    
            self.active_sessions[schedule_id][username].append(websocket)
            
    async def disconnect(self, schedule_id: str, username: str, websocket: WebSocket = None):
        async with self._mutex:
            locks_to_free = []
            if schedule_id in self.active_sessions:
                if username in self.active_sessions[schedule_id]:
                    if websocket and websocket in self.active_sessions[schedule_id][username]:
                        self.active_sessions[schedule_id][username].remove(websocket)
                    
                    # If no more websockets for this user, completely remove them and free their locks
                    if not self.active_sessions[schedule_id][username]:
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
            
        disconnected_ws = []
        # Clone the dict to avoid RuntimeError
        connections = dict(self.active_sessions[schedule_id])
        
        for username, ws_list in connections.items():
            if exclude and username == exclude:
                continue
            for ws in ws_list:
                try:
                    await ws.send_json(message)
                except Exception:
                    disconnected_ws.append((username, ws))
                
        # Clean up any that failed
        for user, ws in disconnected_ws:
            await self.disconnect(schedule_id, user, ws)

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
            return False

# Singleton instance
manager = CollaborationManager()
