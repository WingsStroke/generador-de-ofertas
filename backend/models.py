from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

class BlockStatus(str, Enum):
    CONFIRMED = "confirmed"
    INFERRED = "inferred"
    ERROR = "error"
    UNKNOWN = "unknown"

class ScheduleBlock(BaseModel):
    """Representa un bloque individual de clase dentro de una celda"""
    model_config = ConfigDict(extra="ignore")
    
    id: str
    materia: Optional[str] = None
    materia_id: Optional[str] = None
    grupo: Optional[str] = None
    docente: Optional[str] = None
    aula: Optional[str] = None
    nivel_confianza: float = 0.0
    estado: BlockStatus = BlockStatus.UNKNOWN
    celda_origen: Optional[str] = None
    texto_original: Optional[str] = None

class ScheduleCell(BaseModel):
    """Representa una celda del horario con múltiples bloques"""
    model_config = ConfigDict(extra="ignore")
    
    dia: str
    hora_inicio: str
    hora_fin: str
    bloques: List[ScheduleBlock] = []
    celda_ref: Optional[str] = None

class ExcelCell(BaseModel):
    """Representa una celda del Excel original para preview"""
    model_config = ConfigDict(extra="ignore")
    
    ref: str
    value: Optional[str] = None
    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1
    is_merged: bool = False

class ProcessedSchedule(BaseModel):
    """Horario completo procesado"""
    model_config = ConfigDict(extra="ignore")
    
    id: str
    nombre_archivo: str
    fecha_procesamiento: datetime
    programa_id: str
    programa_nombre: str
    semestre: Optional[str] = None
    hojas: List[str] = []
    hoja_actual: str = ""
    celdas: List[ScheduleCell] = []
    estructura_dias: List[str] = []
    estructura_horas: List[Dict[str, str]] = []
    excel_preview: List[ExcelCell] = []
    nivel_confianza_global: float = 0.0

class ProgramaAcademico(BaseModel):
    """Programa académico disponible"""
    model_config = ConfigDict(extra="ignore")
    
    id: str
    nombre: str
    total_materias: int

class UploadResponse(BaseModel):
    """Respuesta al subir un archivo"""
    schedule_id: str
    message: str
    confianza_global: float

class BlockUpdate(BaseModel):
    """Actualización de un bloque"""
    materia: Optional[str] = None
    materia_id: Optional[str] = None
    grupo: Optional[str] = None
    docente: Optional[str] = None
    aula: Optional[str] = None

class BlockMove(BaseModel):
    """Movimiento de un bloque a una nueva celda"""
    block_id: str
    from_dia: str
    from_hora_inicio: str
    to_dia: str
    to_hora_inicio: str
    to_hora_fin: str

class Subject(BaseModel):
    """Materia del diccionario académico"""
    model_config = ConfigDict(extra="ignore")
    
    id: str
    nombre_oficial: str
    codigo: Optional[str] = None
    creditos: Optional[int] = None
