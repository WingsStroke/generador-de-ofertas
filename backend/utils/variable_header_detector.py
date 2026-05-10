"""
VariableHeaderDetector - Detecta fila de headers cuando varía entre hojas
"""
import re
from typing import Optional, List, Tuple


class VariableHeaderDetector:
    """
    Detecta automáticamente la fila que contiene los headers del horario,
    incluso cuando varía entre diferentes hojas o versiones de archivo.
    """
    
    DIA_KEYWORDS = ['LUNES', 'MARTES', 'MIERCOLES', 'MIERCOLES', 'JUEVES', 'VIERNES', 'SABADO', 'SABADO']
    HEADER_INDICATORS = ['HORA', 'HORARIO', 'DIA', 'ASIGNATURA', 'MATERIA']
    
    def detect_header_row(self, sheet, max_scan: int = 10) -> int:
        """
        Encuentra la fila más probable que contiene los headers de días.
        
        Args:
            sheet: Hoja de Excel (openpyxl)
            max_scan: Máximo número de filas a escanear
            
        Returns:
            Número de fila con los headers (1-based)
        """
        scores = []
        
        for row_idx in range(1, min(max_scan + 1, sheet.max_row + 1)):
            score = self._score_row_as_header(sheet, row_idx)
            scores.append((row_idx, score))
        
        # Encontrar fila con mayor score
        best_row = max(scores, key=lambda x: x[1])
        
        # Si no hay buen candidato, default a fila 2 o 3
        if best_row[1] < 2:
            # Intentar detectar título del semestre en filas 1-2
            for row_idx in [1, 2]:
                if self._looks_like_title_row(sheet, row_idx):
                    return row_idx + 1  # Headers probablemente en siguiente fila
            return 3  # Default tradicional
        
        return best_row[0]
    
    def _score_row_as_header(self, sheet, row_idx: int) -> float:
        """
        Calcula un score indicando qué tan probable es que esta fila sea headers.
        
        Scoring:
        - +2 por cada día de la semana encontrado
        - +2 si encuentra "HORA" en columna 1
        - +2 si encuentra indicadores de catálogo inline (col 8+)
        - +1 por cada indicador de header genérico
        """
        score = 0.0
        dias_found = 0
        
        # Escanear columnas relevantes
        for col_idx in range(1, min(15, sheet.max_column + 1)):
            cell = sheet.cell(row=row_idx, column=col_idx)
            if not cell.value:
                continue
            
            val_upper = str(cell.value).upper().strip()
            
            # Buscar días de la semana
            for keyword in self.DIA_KEYWORDS:
                if keyword in val_upper:
                    dias_found += 1
                    score += 2
                    break
            
            # Buscar indicadores de catálogo inline (columnas 8+)
            if col_idx >= 8:
                if any(ind in val_upper for ind in ['ASIGNATURA', 'MATERIA', 'NOMBRE']):
                    score += 2
                if val_upper in ['HORAS', 'CODIGO', 'CODIGO DE ASIGNATURA', 'GRUPO']:
                    score += 1
            
            # Buscar indicadores genéricos de header
            for indicator in self.HEADER_INDICATORS:
                if indicator in val_upper and col_idx <= 7:
                    score += 1
        
        # Bonus por HORA en columna 1
        col1_value = sheet.cell(row=row_idx, column=1).value
        if col1_value and 'HORA' in str(col1_value).upper():
            score += 2
        
        # Bonus por tener múltiples días
        if dias_found >= 5:
            score += 3
        elif dias_found >= 3:
            score += 1
        
        return score
    
    def _looks_like_title_row(self, sheet, row_idx: int) -> bool:
        """
        Detecta si una fila parece ser título (ej: "SEMESTRE I").
        """
        for col_idx in range(1, min(5, sheet.max_column + 1)):
            cell = sheet.cell(row=row_idx, column=col_idx)
            if cell.value:
                val_upper = str(cell.value).upper()
                if any(keyword in val_upper for keyword in ['SEMESTRE', 'SEDE', 'PROGRAMA', 'INGENIERIA']):
                    return True
        return False
    
    def detect_structure(self, sheet, max_scan: int = 10) -> dict:
        """
        Detecta la estructura completa de la hoja.
        
        Returns:
            Dict con:
            - header_row: fila de headers
            - dias_cols: lista de (col_idx, nombre_dia)
            - hora_col: columna de horas (normalmente 1)
            - has_inline_catalog: bool
            - catalog_cols: dict con columnas del catálogo si existe
        """
        header_row = self.detect_header_row(sheet, max_scan)
        
        # Detectar columnas de días
        dias_cols = []
        for col_idx in range(1, min(10, sheet.max_column + 1)):
            cell = sheet.cell(row=header_row, column=col_idx)
            if cell.value:
                val_upper = str(cell.value).upper().strip()
                for dia in self.DIA_KEYWORDS:
                    if dia in val_upper:
                        # Mapear a abreviatura estándar
                        abbr = self._dia_to_abbr(dia)
                        dias_cols.append((col_idx, abbr))
                        break
        
        # Detectar catálogo inline
        catalog_info = self._detect_inline_catalog(sheet, header_row)
        
        return {
            'header_row': header_row,
            'dias_cols': dias_cols,
            'hora_col': 1,  # Asumimos columna A
            'has_inline_catalog': catalog_info is not None,
            'catalog_cols': catalog_info
        }
    
    def _detect_inline_catalog(self, sheet, header_row: int) -> Optional[dict]:
        """
        Detecta si existe un catálogo inline y sus columnas.
        """
        catalog_cols = {}
        
        for col_idx in range(7, min(15, sheet.max_column + 1)):
            cell = sheet.cell(row=header_row, column=col_idx)
            if not cell.value:
                continue
            
            val_upper = str(cell.value).upper().strip()
            
            if any(keyword in val_upper for keyword in ['ASIGNATURA', 'NOMBRE', 'MATERIA']):
                catalog_cols['nombre'] = col_idx
            elif val_upper == 'HORAS' or 'HORA' in val_upper:
                catalog_cols['horas'] = col_idx
            elif 'CODIGO' in val_upper or 'CÓDIGO' in val_upper:
                catalog_cols['codigo'] = col_idx
            elif val_upper == 'GRUPO':
                catalog_cols['grupo'] = col_idx
        
        # Es catálogo si tiene al menos nombre y alguna columna adicional
        if 'nombre' in catalog_cols and len(catalog_cols) >= 2:
            return catalog_cols
        
        return None
    
    def _dia_to_abbr(self, dia: str) -> str:
        """Convierte nombre de día a abreviatura."""
        mapping = {
            'LUNES': 'L',
            'MARTES': 'M',
            'MIERCOLES': 'W',
            'MIERCOLES': 'W',
            'JUEVES': 'J',
            'VIERNES': 'V',
            'SABADO': 'S',
            'SABADO': 'S'
        }
        return mapping.get(dia, dia[0])
    
    def __repr__(self):
        return "VariableHeaderDetector()"
