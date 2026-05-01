import openpyxl
from openpyxl.utils import get_column_letter
from typing import List, Dict, Tuple, Optional
import re

class ExcelReader:
    """Lee archivos Excel y detecta la estructura del horario"""
    
    def __init__(self, file_path: str):
        self.workbook = openpyxl.load_workbook(file_path, data_only=True)
        self.sheets = self.workbook.sheetnames
        self.current_sheet = self.workbook.active
        
    def set_sheet(self, sheet_name: str):
        """Cambia la hoja activa"""
        if sheet_name in self.sheets:
            self.current_sheet = self.workbook[sheet_name]
            return True
        return False
    
    def get_all_sheets(self) -> List[str]:
        """Obtiene nombres de todas las hojas"""
        return self.sheets
        
    def detect_schedule_structure(self) -> Tuple[int, int, List[str], List[Tuple[str, str]]]:
        """Detecta la estructura del horario: fila inicio, columna inicio, días, horas"""
        dias_semana = ["LUNES", "MARTES", "MIÉRCOLES", "MIERCOLES", "JUEVES", "VIERNES", "SÁBADO", "SABADO", "HORA"]

        def _matches_keyword(text: str, keyword: str) -> bool:
            """Match keyword as a standalone word (avoids 'HORARIO' matching 'HORA')."""
            return re.search(rf'\b{re.escape(keyword)}\b', text) is not None

        start_row = None
        start_col = None
        dias_encontrados = []

        # Pick the row that contains the MOST day-keyword cells (header row likely has 5+ days)
        best_row = None
        best_count = 0
        best_first_col = None
        for row_idx, row in enumerate(self.current_sheet.iter_rows(max_row=20), 1):
            row_count = 0
            first_match_col = None
            for col_idx, cell in enumerate(row, 1):
                if cell.value and isinstance(cell.value, str):
                    cell_upper = cell.value.strip().upper()
                    if any(_matches_keyword(cell_upper, dia) for dia in dias_semana):
                        row_count += 1
                        if first_match_col is None:
                            first_match_col = col_idx
            if row_count > best_count:
                best_count = row_count
                best_row = row_idx
                best_first_col = first_match_col

        if best_row and best_count >= 2:
            start_row = best_row
            start_col = best_first_col

        if not start_row:
            start_row = 1
            start_col = 1

        for cell in self.current_sheet[start_row]:
            if cell.value and isinstance(cell.value, str):
                val_upper = cell.value.strip().upper()
                for dia in ["LUNES", "MARTES", "MIÉRCOLES", "MIERCOLES", "JUEVES", "VIERNES", "SÁBADO", "SABADO"]:
                    if _matches_keyword(val_upper, dia):
                        dia_corto = self._dia_to_short(dia)
                        if dia_corto not in dias_encontrados:
                            dias_encontrados.append(dia_corto)

        if not dias_encontrados:
            dias_encontrados = ["L", "M", "W", "J", "V"]

        horas = self._extract_time_slots(start_row + 1)

        return start_row, start_col, dias_encontrados, horas
    
    def _dia_to_short(self, dia: str) -> str:
        """Convierte nombre de día completo a abreviatura"""
        mapping = {
            "LUNES": "L",
            "MARTES": "M",
            "MIÉRCOLES": "W",
            "MIERCOLES": "W",
            "JUEVES": "J",
            "VIERNES": "V",
            "SÁBADO": "S",
            "SABADO": "S"
        }
        return mapping.get(dia, dia[0])
    
    def _extract_time_slots(self, start_row: int) -> List[Tuple[str, str]]:
        """Extrae las franjas horarias"""
        time_pattern = re.compile(r'(\d{1,2})[:\s]*(\d{2})')
        horas = []
        
        for row in self.current_sheet.iter_rows(min_row=start_row, max_row=start_row + 50):
            cell_value = row[0].value
            if cell_value and isinstance(cell_value, str):
                matches = time_pattern.findall(cell_value)
                if len(matches) >= 2:
                    hora_inicio = f"{matches[0][0].zfill(2)}:{matches[0][1]}"
                    hora_fin = f"{matches[1][0].zfill(2)}:{matches[1][1]}"
                    horas.append((hora_inicio, hora_fin))
        
        if not horas:
            horas = [("07:00", "08:40"), ("08:50", "10:30"), ("10:40", "12:20"), 
                     ("12:30", "14:10"), ("14:20", "16:00"), ("16:10", "17:50"), 
                     ("18:00", "19:40"), ("19:50", "21:30")]
        
        return horas
    
    def get_cell_content(self, row: int, col: int) -> Optional[str]:
        """Obtiene el contenido de una celda"""
        cell = self.current_sheet.cell(row=row, column=col)
        return str(cell.value).strip() if cell.value else None
    
    def get_merged_cells(self) -> List[Dict]:
        """Obtiene información de celdas fusionadas"""
        merged_cells = []
        for merged_range in self.current_sheet.merged_cells.ranges:
            min_col, min_row, max_col, max_row = merged_range.bounds
            merged_cells.append({
                "ref": str(merged_range),
                "min_row": min_row,
                "min_col": min_col,
                "max_row": max_row,
                "max_col": max_col,
                "rowspan": max_row - min_row + 1,
                "colspan": max_col - min_col + 1
            })
        return merged_cells
    
    def extract_schedule_cells(self) -> List[Dict]:
        """Extrae todas las celdas relevantes del horario"""
        start_row, start_col, dias, horas = self.detect_schedule_structure()
        merged_info = self.get_merged_cells()
        
        cells_data = []
        dias_keywords = ["LUNES", "MARTES", "MIÉRCOLES", "MIERCOLES", "JUEVES", "VIERNES", "SÁBADO", "SABADO"]
        
        for hora_idx, (hora_inicio, hora_fin) in enumerate(horas):
            for dia_idx, dia in enumerate(dias):
                row = start_row + 1 + hora_idx
                col = start_col + 1 + dia_idx
                
                content = self.get_cell_content(row, col)
                
                if content and content.lower() not in ['none', 'nan', '']:
                    is_day_header = any(d in content.upper() for d in dias_keywords)
                    
                    if not is_day_header:
                        cell_ref = f"{get_column_letter(col)}{row}"
                        cells_data.append({
                            "dia": dia,
                            "hora_inicio": hora_inicio,
                            "hora_fin": hora_fin,
                            "texto": content,
                            "celda_ref": cell_ref,
                            "row": row,
                            "col": col
                        })
        
        return cells_data
    
    def get_preview_grid(self, max_rows: int = 50, max_cols: int = 10) -> List[Dict]:
        """Genera una representación del Excel para preview"""
        preview_cells = []
        merged_info = {str(m["ref"]): m for m in self.get_merged_cells()}
        
        for row_idx in range(1, min(max_rows + 1, self.current_sheet.max_row + 1)):
            for col_idx in range(1, min(max_cols + 1, self.current_sheet.max_column + 1)):
                cell = self.current_sheet.cell(row=row_idx, column=col_idx)
                cell_ref = f"{get_column_letter(col_idx)}{row_idx}"
                
                is_merged = False
                rowspan = 1
                colspan = 1
                
                for merged_range, info in merged_info.items():
                    if (info["min_row"] <= row_idx <= info["max_row"] and 
                        info["min_col"] <= col_idx <= info["max_col"]):
                        is_merged = True
                        if row_idx == info["min_row"] and col_idx == info["min_col"]:
                            rowspan = info["rowspan"]
                            colspan = info["colspan"]
                        break
                
                preview_cells.append({
                    "ref": cell_ref,
                    "value": str(cell.value) if cell.value else None,
                    "row": row_idx,
                    "col": col_idx,
                    "rowspan": rowspan,
                    "colspan": colspan,
                    "is_merged": is_merged
                })
        
        return preview_cells
    
    def close(self):
        """Cierra el workbook"""
        if self.workbook:
            self.workbook.close()
