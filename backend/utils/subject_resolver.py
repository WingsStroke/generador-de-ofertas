from typing import Dict, Optional

from state import programas_dict
from storage.subjects_storage import subjects_storage
from utils.subject_utils import derive_subject_id, merge_subject_dicts, normalize_subject_name


def get_base_subjects(program_id: str) -> Dict[str, Dict]:
    return programas_dict.get(program_id, {}).get("diccionario", {})


def get_global_subjects() -> Dict[str, Dict]:
    return subjects_storage.get_all_dict()


def get_merged_subjects(program_id: str) -> Dict[str, Dict]:
    return merge_subject_dicts(get_base_subjects(program_id), get_global_subjects())


def is_base_subject(program_id: str, subject_id: str) -> bool:
    return subject_id in get_base_subjects(program_id)


def _find_by_normalized_name(subject_dict: Dict[str, Dict], materia: str) -> Optional[tuple]:
    target = normalize_subject_name(materia)
    if not target:
        return None
    for sid, data in subject_dict.items():
        if normalize_subject_name(data.get("nombre_oficial", "")) == target:
            return sid, data
    return None


def resolve_subject_fields(
    program_id: str,
    materia: Optional[str],
    materia_id: Optional[str] = None,
    codigo: Optional[str] = None,
    creditos: Optional[int] = None,
) -> Dict:
    base_dict = get_base_subjects(program_id)
    global_dict = get_global_subjects()

    nombre = (materia or "").strip()
    selected_id = (materia_id or "").strip() or None

    if selected_id and selected_id in base_dict:
        base = base_dict[selected_id]
        return {
            "id": selected_id,
            "nombre": base.get("nombre_oficial") or nombre,
            "codigo": base.get("codigo"),
            "creditos": base.get("creditos"),
            "source": "base",
        }

    if selected_id and selected_id in global_dict:
        glob = global_dict[selected_id]
        return {
            "id": selected_id,
            "nombre": glob.get("nombre_oficial") or nombre,
            "codigo": glob.get("codigo"),
            "creditos": glob.get("creditos"),
            "source": "global",
        }

    by_name_base = _find_by_normalized_name(base_dict, nombre)
    if by_name_base:
        sid, base = by_name_base
        return {
            "id": sid,
            "nombre": base.get("nombre_oficial") or nombre,
            "codigo": base.get("codigo"),
            "creditos": base.get("creditos"),
            "source": "base",
        }

    by_name_global = _find_by_normalized_name(global_dict, nombre)
    if by_name_global:
        sid, glob = by_name_global
        return {
            "id": sid,
            "nombre": glob.get("nombre_oficial") or nombre,
            "codigo": glob.get("codigo"),
            "creditos": glob.get("creditos"),
            "source": "global",
        }

    generated_id = selected_id or derive_subject_id(nombre)
    return {
        "id": generated_id,
        "nombre": nombre,
        "codigo": codigo,
        "creditos": creditos,
        "source": "manual",
    }
