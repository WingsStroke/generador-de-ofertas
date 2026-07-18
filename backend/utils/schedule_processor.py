import os
import uuid
import re
from datetime import datetime, timezone
from typing import Dict, List
from utils.excel_reader import ExcelReader
from utils.text_cleaner import TextCleaner
from utils.semantic_parser import SemanticParser, looks_like_modality_group
from utils.subject_matcher import SubjectMatcher
from utils.subject_utils import derive_subject_id
from utils.time_utils import calcular_bloques_horarios
from models import (
    ScheduleBlock, ScheduleCell, ProcessedSchedule, 
    ExcelCell, BlockStatus, TimeSlot
)
from storage.teachers_storage import teachers_storage

class ScheduleProcessor:
    """Procesa archivos Excel y genera horarios estructurados"""
    
    def __init__(self, subject_dict: Dict):
        self.subject_dict = subject_dict
        self.matcher = SubjectMatcher(subject_dict)
    
    def process_file(self, file_path: str, filename: str, programa_id: str = None, programa_nombre: str = None, process_all_sheets: bool = True) -> ProcessedSchedule:
        """
        Procesa un archivo Excel completo.
        
        El ExcelReader se cierra automáticamente al finalizar, incluso si hay errores.
        """
        reader = ExcelReader(file_path)
        
        # Cachear la lista de docentes una sola vez para evitar I/O por cada bloque
        teachers_list = teachers_storage.get_all()
        
        try:
            all_sheets = reader.get_all_sheets()
            
            if not process_all_sheets:
                current_sheet = all_sheets[0] if all_sheets else "Sheet1"
                reader.set_sheet(current_sheet)
                
                schedule_cells = reader.extract_schedule_cells()
                preview_grid = reader.get_preview_grid()
                start_row, start_col, dias, horas = reader.detect_schedule_structure()
                
                processed_cells = []
                merged_index = {}
                total_confidence = 0.0
                total_blocks = 0

                for cell_data in schedule_cells:
                    processed_cell = self._process_cell(cell_data, teachers_list)
                    key = (processed_cell.dia, processed_cell.hora_inicio)
                    if key in merged_index:
                        existing = processed_cells[merged_index[key]]
                        existing.bloques.extend(processed_cell.bloques)
                    else:
                        merged_index[key] = len(processed_cells)
                        processed_cells.append(processed_cell)

                processed_cells = self._deduplicate_blocks(processed_cells)
                for cell in processed_cells:
                    for block in cell.bloques:
                        total_confidence += block.nivel_confianza
                        total_blocks += 1
                
                global_confidence = total_confidence / total_blocks if total_blocks > 0 else 0.0
                
                estructura_horas = [{"inicio": h[0], "fin": h[1]} for h in horas]
                preview_cells = [ExcelCell(**cell) for cell in preview_grid]
                
                schedule = ProcessedSchedule(
                    id=str(uuid.uuid4()),
                    nombre_archivo=filename,
                    fecha_procesamiento=datetime.now(timezone.utc),
                    programa_id=programa_id or "unknown",
                    programa_nombre=programa_nombre or "Programa Desconocido",
                    hojas=all_sheets,
                    hojas_data={},
                    hoja_actual=current_sheet,
                    celdas=processed_cells,
                    estructura_dias=dias,
                    estructura_horas=estructura_horas,
                    excel_preview=preview_cells,
                    nivel_confianza_global=global_confidence
                )
                
                return schedule
            
            # Si llegamos aquí, process_all_sheets es True
            # El código continúa después del bloque finally
            
            hojas_data = {}
            total_confidence_all = 0.0
            total_blocks_all = 0
            
            for sheet_name in all_sheets:
                reader.set_sheet(sheet_name)

                # Extraer celdas usando merged_handler para mejor manejo de celdas fusionadas
                schedule_cells = reader.extract_schedule_cells(use_merged_handler=True)
                preview_grid = reader.get_preview_grid()
                start_row, start_col, dias, horas = reader.detect_schedule_structure()

                # Detectar catálogo: primero intentar inline, luego hoja separada
                catalog_entries = []
                
                # 1. Intentar catálogo inline (formato Alimentos 2026)
                inline_catalog = reader.extract_inline_catalog(header_row=start_row)
                if inline_catalog:
                    from utils.catalog_reader import _normalize, _norm_grupo
                    # Convertir InlineCatalogEntry a formato dict esperado por _enrich_block_from_catalog
                    # Incluyendo claves normalizadas que espera find_match
                    catalog_entries = [
                        {
                            'materia': entry.nombre,
                            'horas': entry.horas,
                            'codigo': entry.codigo,
                            'grupo': entry.grupo,
                            'docente': entry.docente,
                            'fila_excel': entry.fila_excel,
                            'materia_norm': _normalize(entry.nombre),
                            'grupo_norm': _norm_grupo(entry.grupo) if entry.grupo else ""
                        }
                        for entry in inline_catalog
                    ]
                
                # 2. Si no hay inline, intentar catálogo en hoja separada
                if not catalog_entries:
                    catalog_info = reader.detect_catalog()
                    catalog_entries = reader.read_catalog_entries(catalog_info) if catalog_info else []

                processed_cells = []
                merged_index = {}
                total_confidence = 0.0
                total_blocks = 0

                for cell_data in schedule_cells:
                    processed_cell = self._process_cell(cell_data, teachers_list)

                    if catalog_entries:
                        for blk in processed_cell.bloques:
                            self._enrich_block_from_catalog(blk, catalog_entries)

                    key = (processed_cell.dia, processed_cell.hora_inicio)
                    if key in merged_index:
                        existing = processed_cells[merged_index[key]]
                        existing.bloques.extend(processed_cell.bloques)
                    else:
                        merged_index[key] = len(processed_cells)
                        processed_cells.append(processed_cell)

                processed_cells = self._deduplicate_blocks(processed_cells)
                for cell in processed_cells:
                    for block in cell.bloques:
                        total_confidence += block.nivel_confianza
                        total_blocks += 1
                
                sheet_confidence = total_confidence / total_blocks if total_blocks > 0 else 0.0
                
                total_confidence_all += total_confidence
                total_blocks_all += total_blocks
                
                estructura_horas = [{"inicio": h[0], "fin": h[1]} for h in horas]
                preview_cells = [ExcelCell(**cell) for cell in preview_grid]
                
                hojas_data[sheet_name] = {
                    "nombre": sheet_name,
                    "celdas": [c.model_dump() for c in processed_cells],
                    "estructura_dias": dias,
                    "estructura_horas": estructura_horas,
                    "excel_preview": [e.model_dump() for e in preview_cells],
                    "nivel_confianza": sheet_confidence
                }
            
            global_confidence = total_confidence_all / total_blocks_all if total_blocks_all > 0 else 0.0
            
            first_sheet = all_sheets[0] if all_sheets else "Sheet1"
            first_sheet_data = hojas_data.get(first_sheet, {})
            
            schedule = ProcessedSchedule(
                id=str(uuid.uuid4()),
                nombre_archivo=filename,
                fecha_procesamiento=datetime.now(timezone.utc),
                programa_id=programa_id or "unknown",
                programa_nombre=programa_nombre or "Programa Desconocido",
                hojas=all_sheets,
                hojas_data=hojas_data,
                hoja_actual=first_sheet,
                celdas=[ScheduleCell(**c) for c in first_sheet_data.get("celdas", [])],
                estructura_dias=first_sheet_data.get("estructura_dias", []),
                estructura_horas=first_sheet_data.get("estructura_horas", []),
                excel_preview=[ExcelCell(**e) for e in first_sheet_data.get("excel_preview", [])],
                nivel_confianza_global=global_confidence
            )
            
            return schedule
            
        finally:
            reader.close()
    
    def _deduplicate_blocks(self, cells: List[ScheduleCell]) -> List[ScheduleCell]:
        """Elimina bloques duplicados exactos dentro de cada celda."""
        for cell in cells:
            seen = set()
            unique_blocks = []
            for block in cell.bloques:
                key = (
                    (block.materia or "").strip().lower(),
                    (block.grupo or "").strip().lower(),
                    (block.docente or "").strip().lower(),
                    (block.aula or "").strip().lower(),
                )
                if key not in seen:
                    seen.add(key)
                    unique_blocks.append(block)
            cell.bloques = unique_blocks
        return cells

    def _process_cell(self, cell_data: Dict, teachers_list: List[str] = None) -> ScheduleCell:
        """Procesa una celda individual del horario"""
        texto = cell_data["texto"]
        classes = TextCleaner.split_multiple_classes(texto)
        
        bloques = []
        for class_text in classes:
            multiple_groups = TextCleaner.extract_multiple_groups(class_text)
            
            if multiple_groups:
                for grupo in multiple_groups:
                    modified_text = re.sub(r'[A-Z]\d+[\s,y&/]*', f'{grupo} ', class_text, count=1)
                    block = self._parse_class_block(modified_text, cell_data["celda_ref"], teachers_list, forced_grupo=grupo)
                    self._add_time_slot_to_block(
                        block, 
                        cell_data["dia"], 
                        cell_data["hora_inicio"], 
                        cell_data["hora_fin"]
                    )
                    bloques.append(block)
            else:
                block = self._parse_class_block(class_text, cell_data["celda_ref"], teachers_list)
                self._add_time_slot_to_block(
                    block, 
                    cell_data["dia"], 
                    cell_data["hora_inicio"], 
                    cell_data["hora_fin"]
                )
                bloques.append(block)
        
        return ScheduleCell(
            dia=cell_data["dia"],
            hora_inicio=cell_data["hora_inicio"],
            hora_fin=cell_data["hora_fin"],
            bloques=bloques,
            celda_ref=cell_data["celda_ref"]
        )
    
    def _parse_class_block(self, text: str, celda_ref: str, teachers_list: List[str] = None, forced_grupo: str = None) -> ScheduleBlock:
        """Parsea un bloque de clase individual"""
        if teachers_list is None:
            teachers_list = teachers_storage.get_all()
            
        entities = SemanticParser.extract_entities(text, teachers_list)
        
        grupo = forced_grupo or entities["grupo"]
        
        materia_text = entities["materia"]
        subject_id, subject_name, confidence = self.matcher.match_subject(materia_text)

        if not subject_id:
            subject_id = derive_subject_id(materia_text)

        subject_meta = self.subject_dict.get(subject_id, {}) if subject_id else {}
        
        estado = BlockStatus.UNKNOWN
        if confidence >= 0.9:
            estado = BlockStatus.CONFIRMED
        elif confidence >= 0.7:
            estado = BlockStatus.INFERRED
        elif confidence > 0:
            estado = BlockStatus.INFERRED
        else:
            estado = BlockStatus.UNKNOWN
        
        if not grupo:
            confidence *= 0.8
            if estado == BlockStatus.CONFIRMED:
                estado = BlockStatus.INFERRED
        
        block = ScheduleBlock(
            id=str(uuid.uuid4()),
            materia=subject_name if subject_name else materia_text,
            materia_original=materia_text,
            materia_id=subject_id,
            grupo=grupo,
            docente=entities["docente"],
            origen_docente=entities["origen_docente"],
            # Desde esta version, el aula no se infiere automaticamente.
            # El campo se mantiene para edicion manual por parte del usuario.
            aula=None,
            codigo=subject_meta.get("codigo"),
            creditos=subject_meta.get("creditos"),
            nivel_confianza=confidence,
            estado=estado,
            celda_origen=celda_ref,
            texto_original=entities["texto_limpio"],
            horarios=[]
        )
        
        return block
    
    def _add_time_slot_to_block(self, block: ScheduleBlock, dia: str, hora_inicio: str, hora_fin: str):
        """Agrega un horario a un bloque y calcula los bloques de 50min"""
        bloques_cantidad, minutos = calcular_bloques_horarios(hora_inicio, hora_fin)
        
        time_slot = TimeSlot(
            dia=dia,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            bloques_cantidad=bloques_cantidad
        )
        
        block.horarios.append(time_slot)


    def _enrich_block_from_catalog(self, block: ScheduleBlock, catalog_entries: list):
        """Enriquece un bloque con información del catálogo (docente, grupo, código).

        Reglas:
          - Solo rellena `docente` si el bloque NO tenía docente.
          - Si el bloque no tiene grupo y la materia tiene un único grupo en el catálogo,
            asigna ese grupo automáticamente.
          - Threshold de fuzzy match: 85.
          - Si hay match con (materia + grupo) confirma el bloque (estado=confirmed,
            confianza=1.0).
        """
        from utils.catalog_reader import find_match

        materia_original = block.materia_original or block.materia or ""
        materia_oficial = block.materia or ""
        grupo_text = block.grupo or ""

        match, single_group = find_match(catalog_entries, materia_original, grupo_text, threshold=85)
        
        # Si no hubo match con el texto original, intentar con el oficial procesado
        if not match and materia_oficial != materia_original:
            match, single_group = find_match(catalog_entries, materia_oficial, grupo_text, threshold=85)

        docente_valido = block.docente and not looks_like_modality_group(block.docente)

        if match:
            if (not docente_valido) and match.get("docente"):
                block.docente = match["docente"]
            if match.get("codigo") and not block.codigo:
                block.codigo = match["codigo"]
            block.estado = BlockStatus.CONFIRMED
            block.nivel_confianza = max(block.nivel_confianza, 1.0)
            return

        if single_group and not block.grupo:
            block.grupo = single_group["grupo"]
            if (not docente_valido) and single_group.get("docente"):
                block.docente = single_group["docente"]
            if single_group.get("codigo") and not block.codigo:
                block.codigo = single_group["codigo"]
            if block.estado == BlockStatus.UNKNOWN:
                block.estado = BlockStatus.INFERRED
            block.nivel_confianza = max(block.nivel_confianza, 0.85)
