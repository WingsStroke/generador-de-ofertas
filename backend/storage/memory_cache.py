"""
Memory Cache + JSON Persistence Backend

Implementación de almacenamiento en caché LRU con persistencia en archivos JSON.
Thread-safe usando asyncio.Lock para operaciones de escritura.

Características:
- LRU (Least Recently Used) eviction cuando se alcanza max_size
- TTL (Time To Live) automático para limpieza de datos antiguos
- Persistencia síncrona/async a archivos JSON
- Thread-safe para operaciones concurrentes
"""

import os
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from collections import OrderedDict
import aiofiles
import copy

logger = logging.getLogger(__name__)


class MemoryStorage:
    """
    Backend de almacenamiento en memoria con persistencia JSON.
    
    Usa OrderedDict para implementar LRU (Least Recently Used) caché.
    Cuando se alcanza max_size, se elimina el item menos recientemente usado.
    """
    
    def __init__(self, max_size: int = 100, ttl_hours: int = 168, data_dir: str = './data/schedules'):
        """
        Inicializa el storage en memoria.
        
        Args:
            max_size: Número máximo de horarios en caché
            ttl_hours: Horas antes de que un horario expire automáticamente
            data_dir: Directorio para persistencia de archivos JSON
        """
        self.max_size = max_size
        self.ttl_hours = ttl_hours
        self.data_dir = Path(data_dir)
        
        # Caché LRU: OrderedDict mantiene orden de acceso
        # Key: schedule_id, Value: Dict con datos + metadata
        self._cache: OrderedDict[str, Dict] = OrderedDict()
        
        # Lock para operaciones de escritura (thread-safety)
        self._lock = asyncio.Lock()
        
        # Crear directorio de datos si no existe
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Cargar datos existentes del disco
        self._load_all_from_disk()
        
        # Iniciar thread de limpieza TTL (se inicia manualmente después)
        self._cleanup_task = None
        
        logger.info(f"MemoryStorage inicializado: max_size={max_size}, ttl={ttl_hours}h, data_dir={data_dir}")
    
    def _get_schedule_path(self, schedule_id: str) -> Path:
        """Obtiene la ruta del archivo JSON para un schedule_id."""
        # Usar primeros 2 caracteres para subdirectorio (distribución uniforme)
        subdir = schedule_id[:2] if len(schedule_id) >= 2 else 'xx'
        dir_path = self.data_dir / subdir
        dir_path.mkdir(exist_ok=True)
        return dir_path / f"{schedule_id}.json"
    
    def _load_all_from_disk(self):
        """Carga todos los horarios existentes del disco a caché."""
        if not self.data_dir.exists():
            return
        
        loaded_count = 0
        for subdir in self.data_dir.iterdir():
            if subdir.is_dir():
                for json_file in subdir.glob('*.json'):
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        schedule_id = data.get('id')
                        if schedule_id:
                            # Verificar TTL antes de cargar
                            if not self._is_expired(data):
                                self._cache[schedule_id] = data
                                loaded_count += 1
                            else:
                                # Eliminar archivo expirado
                                json_file.unlink()
                                logger.debug(f"Archivo expirado eliminado: {json_file}")
                    
                    except Exception as e:
                        logger.warning(f"Error cargando {json_file}: {e}")
        
        # Reordenar por orden de creación (más antiguo al final para LRU)
        sorted_items = sorted(
            self._cache.items(),
            key=lambda x: x[1].get('_created_at', '')
        )
        self._cache = OrderedDict(sorted_items)
        
        logger.info(f"Cargados {loaded_count} horarios desde disco")
    
    def _is_expired(self, data: Dict) -> bool:
        """Verifica si un horario ha expirado según TTL."""
        created_at = data.get('_created_at')
        if not created_at:
            return False
        
        try:
            created = datetime.fromisoformat(created_at)
            cutoff = datetime.utcnow() - timedelta(hours=self.ttl_hours)
            return created < cutoff
        except:
            return False
    
    async def _save_to_disk(self, schedule_id: str, data: Dict):
        """Guarda un horario a disco de forma async."""
        try:
            file_path = self._get_schedule_path(schedule_id)
            
            # Usar escritura async
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
            
            logger.debug(f"Guardado {schedule_id} en {file_path}")
        
        except Exception as e:
            logger.error(f"Error guardando {schedule_id} a disco: {e}")
            raise
    
    async def _delete_from_disk(self, schedule_id: str):
        """Elimina un horario del disco."""
        try:
            file_path = self._get_schedule_path(schedule_id)
            if file_path.exists():
                file_path.unlink()
                logger.debug(f"Eliminado {file_path}")
        
        except Exception as e:
            logger.error(f"Error eliminando {schedule_id} de disco: {e}")
    
    async def create(self, data: Dict) -> str:
        """
        Crea un nuevo horario en caché y disco.
        
        Args:
            data: Datos del horario (debe incluir 'id')
            
        Returns:
            schedule_id del horario creado
        """
        schedule_id = data.get('id')
        if not schedule_id:
            raise ValueError("Los datos deben incluir 'id'")
        
        async with self._lock:
            # Agregar metadata de control
            data['_backend'] = 'memory'
            data['_created_at'] = datetime.utcnow().isoformat()
            data['_updated_at'] = data['_created_at']
            data['_v'] = data.get('_v', 0)
            
            # Agregar a caché (se mueve al final = más reciente)
            self._cache[schedule_id] = data
            self._cache.move_to_end(schedule_id)
            
            # Evict si excedemos max_size
            while len(self._cache) > self.max_size:
                oldest_id, oldest_data = self._cache.popitem(last=False)
                logger.info(f"Evicting LRU item: {oldest_id}")
                # El archivo en disco se mantiene, solo se saca de caché
        
        # Guardar a disco (fuera del lock para no bloquear)
        await self._save_to_disk(schedule_id, data)
        
        logger.info(f"Creado horario {schedule_id}")
        return schedule_id
    
    async def get(self, schedule_id: str) -> Optional[Dict]:
        """
        Obtiene un horario por ID.
        
        Intenta caché primero, luego disco si no está en caché.
        """
        async with self._lock:
            if schedule_id in self._cache:
                # Mover al final (más recientemente usado)
                self._cache.move_to_end(schedule_id)
                data = self._cache[schedule_id]
                
                # Verificar TTL
                if self._is_expired(data):
                    logger.info(f"Horario expirado: {schedule_id}")
                    self._cache.pop(schedule_id, None)
                    await self._delete_from_disk(schedule_id)
                    return None
                
                return copy.deepcopy(data)  # Deep copy para evitar mutaciones externas
        
        # Intentar cargar del disco si no está en caché
        try:
            file_path = self._get_schedule_path(schedule_id)
            if not file_path.exists():
                return None
            
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
            
            # Verificar TTL
            if self._is_expired(data):
                logger.info(f"Horario expirado en disco: {schedule_id}")
                await self._delete_from_disk(schedule_id)
                return None
            
            # Agregar a caché
            async with self._lock:
                self._cache[schedule_id] = data
                self._cache.move_to_end(schedule_id)
            
            return copy.deepcopy(data)
        
        except Exception as e:
            logger.error(f"Error cargando {schedule_id} de disco: {e}")
            return None
    
    async def update(self, schedule_id: str, update_fn: Callable[[Dict], None]) -> bool:
        """
        Actualiza un horario de forma atómica.
        
        Args:
            schedule_id: ID del horario
            update_fn: Función que modifica los datos in-place
            
        Returns:
            True si se actualizó, False si no se encontró
        """
        async with self._lock:
            # Obtener datos actuales
            if schedule_id in self._cache:
                data = self._cache[schedule_id]
                # Recargar del disco por si acaso
                file_path = self._get_schedule_path(schedule_id)
                if file_path.exists():
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                    except:
                        pass
            else:
                # Intentar cargar del disco
                file_path = self._get_schedule_path(schedule_id)
                if not file_path.exists():
                    return False
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except:
                    return False
            
            # Verificar TTL
            if self._is_expired(data):
                self._cache.pop(schedule_id, None)
                await self._delete_from_disk(schedule_id)
                return False
            
            # Aplicar actualización
            try:
                update_fn(data)
            except Exception as e:
                logger.error(f"Error en update_fn para {schedule_id}: {e}")
                raise
            
            # Actualizar metadata
            data['_updated_at'] = datetime.utcnow().isoformat()
            data['_v'] = data.get('_v', 0) + 1
            
            # Guardar en caché
            self._cache[schedule_id] = data
            self._cache.move_to_end(schedule_id)
        
        # Guardar a disco (fuera del lock)
        await self._save_to_disk(schedule_id, data)
        
        logger.debug(f"Actualizado {schedule_id} (v{data['_v']})")
        return True
    
    async def delete(self, schedule_id: str) -> bool:
        """Elimina un horario de caché y disco."""
        async with self._lock:
            existed = schedule_id in self._cache
            if existed:
                del self._cache[schedule_id]
        
        # Eliminar de disco (fuera del lock)
        await self._delete_from_disk(schedule_id)
        
        if existed:
            logger.info(f"Eliminado {schedule_id}")
        
        return existed
    
    async def list_all(self, limit: int = 1000) -> List[Dict]:
        """Lista todos los horarios no expirados."""
        result = []
        
        async with self._lock:
            # Copiar keys para evitar modificación durante iteración
            keys = list(self._cache.keys())
        
        for schedule_id in keys[:limit]:
            data = await self.get(schedule_id)
            if data:
                # Remover campos internos
                data = {k: v for k, v in data.items() if not k.startswith('_') or k in ['_v', '_created_at', '_updated_at']}
                result.append(data)
        
        return result
    
    async def exists(self, schedule_id: str) -> bool:
        """Verifica si un horario existe."""
        async with self._lock:
            if schedule_id in self._cache:
                return not self._is_expired(self._cache[schedule_id])
        
        file_path = self._get_schedule_path(schedule_id)
        return file_path.exists()
    
    def start_cleanup_task(self):
        """Inicia el thread de limpieza TTL periódica. Debe llamarse con un event loop activo."""
        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(3600)  # Cada hora
                    await self._cleanup_expired()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error en cleanup_loop: {e}")
        
        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info("Tarea de limpieza TTL iniciada (cada 1 hora)")
    
    async def _cleanup_expired(self):
        """Limpia horarios expirados."""
        expired_count = 0
        
        async with self._lock:
            keys = list(self._cache.keys())
        
        for schedule_id in keys:
            async with self._lock:
                if schedule_id in self._cache:
                    data = self._cache[schedule_id]
                    if self._is_expired(data):
                        del self._cache[schedule_id]
                        expired_count += 1
                        # Eliminar de disco también
                        await self._delete_from_disk(schedule_id)
        
        if expired_count > 0:
            logger.info(f"Limpiados {expired_count} horarios expirados")
    
    async def close(self):
        """Cierra el storage y libera recursos."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        logger.info("MemoryStorage cerrado")
