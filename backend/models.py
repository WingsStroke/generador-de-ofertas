from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

class BlockStatus(str, Enum):
    CONFIRMED = "confirmed"
    INFERRED = "inferred"
    ERROR = "error"
    UNKNOWN = "unknown"

class TimeSlot(BaseModel):
    """Representa un horario específico (día y rango de horas)"""
    model_config = ConfigDict(extra="ignore")
    
    dia: str
    hora_inicio: str
    hora_fin: str
    bloques_cantidad: int = 0

class ScheduleBlock(BaseModel):
    """Representa un bloque individual de clase dentro de una celda"""
    model_config = ConfigDict(extra="ignore")
    
    id: str
    materia: Optional[str] = None
    materia_original: Optional[str] = None
    materia_id: Optional[str] = None
    grupo: Optional[str] = None
    docente: Optional[str] = None
    origen_docente: Optional[str] = "motor"
    aula: Optional[str] = None
    codigo: Optional[str] = None
    creditos: Optional[int] = None
    nivel_confianza: float = 0.0
    estado: BlockStatus = BlockStatus.UNKNOWN
    celda_origen: Optional[str] = None
    texto_original: Optional[str] = None
    horarios: List[TimeSlot] = []

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

class SheetData(BaseModel):
    """Datos de una hoja específica"""
    model_config = ConfigDict(extra="ignore")
    
    nombre: str
    celdas: List[ScheduleCell] = []
    estructura_dias: List[str] = []
    estructura_horas: List[Dict[str, str]] = []
    excel_preview: List[ExcelCell] = []
    nivel_confianza: float = 0.0

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
    hojas_data: Dict[str, Any] = {}
    hoja_actual: str = ""
    celdas: List[ScheduleCell] = []
    estructura_dias: List[str] = []
    estructura_horas: List[Dict[str, str]] = []
    excel_preview: List[ExcelCell] = []
    nivel_confianza_global: float = 0.0
    historial_cambios: List[Dict[str, Any]] = []

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
    origen_docente: Optional[str] = None
    aula: Optional[str] = None
    codigo: Optional[str] = None
    creditos: Optional[int] = None

class BlockMove(BaseModel):
    """Movimiento de un bloque a una nueva celda"""
    block_id: str
    from_dia: str
    from_hora_inicio: str
    from_hora_fin: str
    to_dia: str
    to_hora_inicio: str
    to_hora_fin: str

class BulkBlockUpdate(BaseModel):
    block_ids: List[str]
    update: BlockUpdate

class BlockCreate(BaseModel):
    sheet: str
    dia: str
    hora_inicio: str
    hora_fin: str
    materia: Optional[str] = None
    materia_id: Optional[str] = None
    grupo: Optional[str] = None
    docente: Optional[str] = None
    aula: Optional[str] = None
    codigo: Optional[str] = None
    creditos: Optional[int] = None

class Subject(BaseModel):
    """Materia del diccionario académico"""
    model_config = ConfigDict(extra="ignore")
    
    id: str
    nombre_oficial: str
    codigo: Optional[str] = None
    creditos: Optional[int] = None

class GlobalSubjectUpsert(BaseModel):
    id: Optional[str] = None
    nombre_oficial: str
    codigo: Optional[str] = None
    creditos: Optional[int] = None

class SubjectMetadataUpdate(BaseModel):
    codigo: Optional[str] = None
    creditos: Optional[int] = None

class GlobalReplaceRequest(BaseModel):
    """Solicitud de búsqueda y reemplazo global"""
    search_text: str
    replace_text: str
    field: str  # "materia", "docente", "aula" o "all"
    scope: str  # "all" o "current"
    current_sheet: Optional[str] = None
    case_sensitive: bool = False
    exact_match: bool = False

