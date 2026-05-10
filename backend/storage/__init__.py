"""
Storage Backend Module

Este módulo proporciona una capa de abstracción sobre el almacenamiento.
Actualmente usa caché en memoria + archivos JSON.

Para reactivar MongoDB en el futuro:
1. Cambiar STORAGE_BACKEND a "mongodb" en el archivo de configuración
2. El sistema automáticamente usará el backend de MongoDB

TTL implementado:
- Memoria: Thread de limpieza manual (default 7 días)
- MongoDB: Índice TTL nativo (cuando se reactive)
"""

import os
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Configuración del backend de almacenamiento
STORAGE_BACKEND = os.environ.get('STORAGE_BACKEND', 'memory')  # 'memory' o 'mongodb'
CACHE_MAX_SIZE = int(os.environ.get('CACHE_MAX_SIZE', '100'))
CACHE_TTL_HOURS = int(os.environ.get('CACHE_TTL_HOURS', '168'))  # 7 días
DATA_DIR = os.environ.get('DATA_DIR', './data/schedules')

# MONGODB-READY: Configuración preservada para reactivación futura
# MONGO_URL = os.environ.get('MONGO_URL')
# DB_NAME = os.environ.get('DB_NAME')


class Storage:
    """
    Fachada unificada para operaciones de almacenamiento.
    
    Proporciona la misma interfaz independientemente del backend:
    - create(data): Crea nuevo horario
    - get(schedule_id): Obtiene horario por ID
    - update(schedule_id, update_fn): Actualiza atómicamente
    - delete(schedule_id): Elimina horario
    - list_all(): Lista todos los horarios
    - exists(schedule_id): Verifica existencia
    """
    
    _instance = None
    _backend = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Inicializa el backend según configuración."""
        if STORAGE_BACKEND == 'mongodb':
            # MONGODB-READY: Reactivar cuando se necesite
            # from .mongodb_backend import MongoDBBackend
            # self._backend = MongoDBBackend()
            # logger.info("Storage backend: MongoDB")
            raise NotImplementedError(
                "MongoDB backend está desactivado temporalmente. "
                "Use STORAGE_BACKEND=memory o reactive la implementación en storage/__init__.py"
            )
        else:
            from .memory_cache import MemoryStorage
            self._backend = MemoryStorage(
                max_size=CACHE_MAX_SIZE,
                ttl_hours=CACHE_TTL_HOURS,
                data_dir=DATA_DIR
            )
            logger.info(f"Storage backend: Memory + JSON (max_size={CACHE_MAX_SIZE}, ttl={CACHE_TTL_HOURS}h)")
    
    async def create(self, data: Dict) -> str:
        """
        Crea un nuevo horario.
        
        Args:
            data: Datos del horario (debe incluir 'id')
            
        Returns:
            schedule_id del horario creado
        """
        return await self._backend.create(data)
    
    async def get(self, schedule_id: str) -> Optional[Dict]:
        """
        Obtiene un horario por ID.
        
        Args:
            schedule_id: ID del horario
            
        Returns:
            Datos del horario o None si no existe
        """
        return await self._backend.get(schedule_id)
    
    async def update(self, schedule_id: str, update_fn) -> bool:
        """
        Actualiza un horario de forma atómica.
        
        Args:
            schedule_id: ID del horario
            update_fn: Función que recibe los datos actuales y los modifica
            
        Returns:
            True si se actualizó, False si no se encontró
        """
        return await self._backend.update(schedule_id, update_fn)
    
    async def delete(self, schedule_id: str) -> bool:
        """
        Elimina un horario.
        
        Args:
            schedule_id: ID del horario
            
        Returns:
            True si se eliminó, False si no existía
        """
        return await self._backend.delete(schedule_id)
    
    async def list_all(self, limit: int = 1000) -> List[Dict]:
        """
        Lista todos los horarios.
        
        Args:
            limit: Límite de resultados
            
        Returns:
            Lista de horarios (sin el campo _id de MongoDB)
        """
        return await self._backend.list_all(limit)
    
    async def exists(self, schedule_id: str) -> bool:
        """
        Verifica si un horario existe.
        
        Args:
            schedule_id: ID del horario
            
        Returns:
            True si existe, False en caso contrario
        """
        return await self._backend.exists(schedule_id)
    
    async def close(self):
        """Cierra el backend y libera recursos."""
        await self._backend.close()
    
    def start_cleanup(self):
        """Inicia la tarea de limpieza TTL. Debe llamarse después de que el event loop esté corriendo."""
        if hasattr(self._backend, 'start_cleanup_task'):
            self._backend.start_cleanup_task()


# Instancia singleton para uso global
storage = Storage()
