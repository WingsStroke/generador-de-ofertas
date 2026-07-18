import logging
import json
from pathlib import Path
from state import programas_dict, processors
from utils.schedule_processor import ScheduleProcessor
from storage.subjects_storage import subjects_storage
from utils.subject_utils import merge_subject_dicts


def _build_merged_subject_dict(program_id: str):
    base_subjects = programas_dict[program_id]["diccionario"]
    global_subjects = subjects_storage.get_all_dict()
    return merge_subject_dicts(base_subjects, global_subjects)


def refresh_program_processor(program_id: str):
    if program_id not in programas_dict:
        return
    merged_subjects = _build_merged_subject_dict(program_id)
    processors[program_id] = ScheduleProcessor(merged_subjects)


def refresh_all_program_processors():
    for program_id in list(programas_dict.keys()):
        refresh_program_processor(program_id)


def get_program_subjects(program_id: str):
    if program_id not in programas_dict:
        return {}
    return _build_merged_subject_dict(program_id)

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
            
            merged_subjects = merge_subject_dicts(subject_dict, subjects_storage.get_all_dict())
            processors[programa_id] = ScheduleProcessor(merged_subjects)
            
            logging.info(f"Programa cargado: {programa_id} con {len(subject_dict)} materias")
        
        except Exception as e:
            logging.error(f"Error cargando programa {programa_id}: {str(e)}")
