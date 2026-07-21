import logging
import json
from pathlib import Path
from state import programas_dict, processors
from utils.schedule_processor import ScheduleProcessor
from storage.subjects_storage import subjects_storage
from utils.subject_utils import merge_subject_dicts, derive_subject_id


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

def _normalize_subject_dict_keys(subject_dict: dict, programa_id: str) -> dict:
    """
    Fuerza que el ID de cada materia se derive SIEMPRE de su nombre oficial
    (sin espacios, sin tildes, sin caracteres especiales), sin importar qué
    clave tenga físicamente el archivo JSON del diccionario. Esto evita que
    un mismo nombre de materia (ej. "Cálculo Diferencial") termine con IDs
    distintos entre programas solo porque algún diccionario incluía el
    código de la asignatura en la clave y otro no.

    Si dentro de un MISMO programa dos materias distintas comparten
    nombre oficial (ej. varias "Electiva de Profundización Profesional"
    con códigos distintos), se les agrega un sufijo numérico (_2, _3, ...)
    para no perder ninguna, en vez de colapsarlas en un solo ID.
    """
    normalized: dict = {}
    for original_key, data in subject_dict.items():
        nombre_oficial = (data or {}).get("nombre_oficial") or original_key
        base_id = derive_subject_id(nombre_oficial)

        canonical_id = base_id
        suffix = 2
        while canonical_id in normalized:
            logging.warning(
                f"[{programa_id}] Nombre de materia duplicado: '{nombre_oficial}' "
                f"(clave original '{original_key}') -> usando ID '{base_id}_{suffix}' "
                f"para no perder la materia."
            )
            canonical_id = f"{base_id}_{suffix}"
            suffix += 1

        if canonical_id != original_key:
            logging.info(f"[{programa_id}] Normalizando ID de materia: '{original_key}' -> '{canonical_id}'")

        normalized[canonical_id] = data

    return normalized


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

            subject_dict = _normalize_subject_dict_keys(subject_dict, programa_id)
            
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
