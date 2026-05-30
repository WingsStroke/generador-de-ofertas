import logging
import json
from pathlib import Path
from state import programas_dict, processors
from utils.schedule_processor import ScheduleProcessor

def load_academic_programs(root_dir: Path):
    """Carga todos los programas académicos disponibles"""
    diccionarios_dir = root_dir / "diccionarios"
    
    if not diccionarios_dir.exists():
        logging.warning(f"Directorio de diccionarios no encontrado: {diccionarios_dir}")
        return
    
    programa_names = {
        "ingenieria_de_sistemas": "Ingeniería de Sistemas",
        "ingenieria_de_alimentos": "Ingeniería de Alimentos",
        "ingenieria_civil": "Ingeniería Civil",
        "ingenieria_quimica": "Ingeniería Química"
    }
    
    for dict_file in diccionarios_dir.glob("*.json"):
        programa_id = dict_file.stem
        
        try:
            with open(dict_file, 'r', encoding='utf-8') as f:
                subject_dict = json.load(f)
            
            programas_dict[programa_id] = {
                "id": programa_id,
                "nombre": programa_names.get(programa_id, programa_id.replace("_", " ").title()),
                "diccionario": subject_dict,
                "total_materias": len(subject_dict)
            }
            
            processors[programa_id] = ScheduleProcessor(subject_dict)
            
            logging.info(f"Programa cargado: {programa_id} con {len(subject_dict)} materias")
        
        except Exception as e:
            logging.error(f"Error cargando programa {programa_id}: {str(e)}")
