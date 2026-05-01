import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List
from utils.excel_reader import ExcelReader
from utils.text_cleaner import TextCleaner
from utils.semantic_parser import SemanticParser
from utils.subject_matcher import SubjectMatcher
from models import (
    ScheduleBlock, ScheduleCell, ProcessedSchedule, 
    ExcelCell, BlockStatus
)

class ScheduleProcessor:
    """Procesa archivos Excel y genera horarios estructurados"""
    
    def __init__(self, subject_dict: Dict):
        self.subject_dict = subject_dict
        self.matcher = SubjectMatcher(subject_dict)
    
    def process_file(self, file_path: str, filename: str, programa_id: str = None, programa_nombre: str = None) -> ProcessedSchedule:
        """Procesa un archivo Excel completo"""
        reader = ExcelReader(file_path)
        
        try:
            schedule_cells = reader.extract_schedule_cells()
            preview_grid = reader.get_preview_grid()
            
            start_row, start_col, dias, horas = reader.detect_schedule_structure()
            
            processed_cells = []
            total_confidence = 0.0
            total_blocks = 0
            
            for cell_data in schedule_cells:
                processed_cell = self._process_cell(cell_data)
                processed_cells.append(processed_cell)
                
                for block in processed_cell.bloques:
                    total_confidence += block.nivel_confianza
                    total_blocks += 1
            
            global_confidence = total_confidence / total_blocks if total_blocks > 0 else 0.0
            
            estructura_horas = [
                {"inicio": h[0], "fin": h[1]} for h in horas
            ]
            
            preview_cells = [ExcelCell(**cell) for cell in preview_grid]
            
            schedule = ProcessedSchedule(
                id=str(uuid.uuid4()),
                nombre_archivo=filename,
                fecha_procesamiento=datetime.now(timezone.utc),
                programa_id=programa_id or "unknown",
                programa_nombre=programa_nombre or "Programa Desconocido",
                celdas=processed_cells,
                estructura_dias=dias,
                estructura_horas=estructura_horas,
                excel_preview=preview_cells,
                nivel_confianza_global=global_confidence
            )
            
            return schedule
            
        finally:
            reader.close()
    
    def _process_cell(self, cell_data: Dict) -> ScheduleCell:
        """Procesa una celda individual del horario"""
        texto = cell_data["texto"]
        classes = TextCleaner.split_multiple_classes(texto)
        
        bloques = []
        for class_text in classes:
            block = self._parse_class_block(class_text, cell_data["celda_ref"])
            bloques.append(block)
        
        return ScheduleCell(
            dia=cell_data["dia"],
            hora_inicio=cell_data["hora_inicio"],
            hora_fin=cell_data["hora_fin"],
            bloques=bloques,
            celda_ref=cell_data["celda_ref"]
        )
    
    def _parse_class_block(self, text: str, celda_ref: str) -> ScheduleBlock:
        """Parsea un bloque de clase individual"""
        entities = SemanticParser.extract_entities(text)
        
        materia_text = entities["materia"]
        subject_id, subject_name, confidence = self.matcher.match_subject(materia_text)
        
        estado = BlockStatus.UNKNOWN
        if confidence >= 0.9:
            estado = BlockStatus.CONFIRMED
        elif confidence >= 0.7:
            estado = BlockStatus.INFERRED
        elif confidence > 0:
            estado = BlockStatus.INFERRED
        else:
            estado = BlockStatus.UNKNOWN
        
        if not entities["grupo"]:
            confidence *= 0.8
            if estado == BlockStatus.CONFIRMED:
                estado = BlockStatus.INFERRED
        
        block = ScheduleBlock(
            id=str(uuid.uuid4()),
            materia=subject_name if subject_name else materia_text,
            materia_id=subject_id,
            grupo=entities["grupo"],
            docente=entities["docente"],
            aula=entities["aula"],
            nivel_confianza=confidence,
            estado=estado,
            celda_origen=celda_ref,
            texto_original=entities["texto_limpio"]
        )
        
        return block
