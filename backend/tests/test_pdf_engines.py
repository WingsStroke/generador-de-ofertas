import os
import sys
import json
from pathlib import Path

# Paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BACKEND_DIR))
OFERTAS_DIR = BACKEND_DIR.parent / "ofertas"

from utils.pdf_converter import pdf_to_xlsx
from utils.excel_reader import ExcelReader
from utils.schedule_processor import ScheduleProcessor

def test_sistemas_pdf_extraction():
    pdf_path = OFERTAS_DIR / "2026-1-Ing_Sistemas.pdf"
    assert pdf_path.exists(), "Systems PDF not found"
    
    # Convert PDF to XLSX
    xlsx_path = pdf_to_xlsx(str(pdf_path))
    assert os.path.exists(xlsx_path), "Temp XLSX file was not created"
    
    try:
        # Analyze structures
        reader = ExcelReader(xlsx_path)
        all_sheets = reader.get_all_sheets()
        assert len(all_sheets) > 5, f"Expected many sheets, found {len(all_sheets)}"
        
        # Test first sheet (Table 1)
        reader.set_sheet("Table 1")
        structures = reader.detect_all_schedule_structures()
        assert len(structures) >= 1
        
        start_row, start_col, dias, horas, end_row = structures[0]
        detected_days = [d[0] for d in dias]
        
        # ALL 5 days should be found now! (L, M, W, J, V)
        for day in ["L", "M", "W", "J", "V"]:
            assert day in detected_days, f"Day {day} was not detected in Table 1"
            
        # Schedule cells count should be healthy
        schedule_cells = reader.extract_schedule_cells(use_merged_handler=True)
        assert len(schedule_cells) > 30, f"Expected >30 cells, found {len(schedule_cells)}"
        
        reader.close()
        
        # Load dictionary
        dic_path = BACKEND_DIR / "diccionarios" / "ingenieria_de_sistemas.json"
        subject_dict = {}
        if dic_path.exists():
            with open(dic_path, 'r', encoding='utf-8') as f:
                subject_dict = json.load(f)
                
        # Run processor
        processor = ScheduleProcessor(subject_dict)
        schedule = processor.process_file(xlsx_path, "2026-1-Ing_Sistemas.pdf", "ingenieria_de_sistemas", "Ingeniería de Sistemas")
        s_dict = schedule.model_dump()
        
        assert len(s_dict["hojas_data"]) > 5
        table1_cells = s_dict["hojas_data"]["Table 1"]["celdas"]
        assert len(table1_cells) > 20
        
    finally:
        if os.path.exists(xlsx_path):
            os.unlink(xlsx_path)

def test_alimentos_pdf_extraction():
    pdf_path = OFERTAS_DIR / "2026-1-ING_ALIMENTOS.pdf"
    assert pdf_path.exists(), "Alimentos PDF not found"
    
    xlsx_path = pdf_to_xlsx(str(pdf_path))
    assert os.path.exists(xlsx_path)
    
    try:
        reader = ExcelReader(xlsx_path)
        all_sheets = reader.get_all_sheets()
        assert len(all_sheets) > 5
        
        # Test Table 6 (was completely corrupted before)
        reader.set_sheet("Table 6")
        structures = reader.detect_all_schedule_structures()
        assert len(structures) >= 1
        
        start_row, start_col, dias, horas, end_row = structures[0]
        detected_days = [d[0] for d in dias]
        
        for day in ["L", "M", "W", "J", "V"]:
            assert day in detected_days, f"Day {day} was not detected in Table 6"
            
        schedule_cells = reader.extract_schedule_cells(use_merged_handler=True)
        # Should have around 30+ cells
        assert len(schedule_cells) > 25, f"Expected >25 cells, found {len(schedule_cells)}"
        
        reader.close()
        
        # Load dictionary
        dic_path = BACKEND_DIR / "diccionarios" / "ingenieria_de_alimentos.json"
        subject_dict = {}
        if dic_path.exists():
            with open(dic_path, 'r', encoding='utf-8') as f:
                subject_dict = json.load(f)
                
        processor = ScheduleProcessor(subject_dict)
        schedule = processor.process_file(xlsx_path, "2026-1-ING_ALIMENTOS.pdf", "ingenieria_de_alimentos", "Ingeniería de Alimentos")
        s_dict = schedule.model_dump()
        
        # Table 6 should have clean courses
        table6_data = s_dict["hojas_data"]["Table 6"]
        assert len(table6_data["celdas"]) > 20
        
        # Verify a sample block doesn't just contain the time labels like "7:00"
        sample_materia = table6_data["celdas"][0]["bloques"][0]["materia"]
        assert "7:" not in sample_materia, "Extracted time label as subject name"
        
    finally:
        if os.path.exists(xlsx_path):
            os.unlink(xlsx_path)

if __name__ == "__main__":
    print("Running test_sistemas_pdf_extraction...")
    test_sistemas_pdf_extraction()
    print("test_sistemas_pdf_extraction passed!")
    
    print("\nRunning test_alimentos_pdf_extraction...")
    test_alimentos_pdf_extraction()
    print("test_alimentos_pdf_extraction passed!")
    
    print("\nALL TESTS PASSED SUCCESSFULLY!")
