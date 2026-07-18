import re
import unicodedata
from typing import Dict


def normalize_subject_name(name: str) -> str:
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", str(name).strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def derive_subject_id(name: str) -> str:
    normalized = normalize_subject_name(name)
    if not normalized:
        return "materia_sin_nombre"
    subject_id = re.sub(r"[^a-z0-9]+", "_", normalized)
    subject_id = re.sub(r"_+", "_", subject_id).strip("_")
    return subject_id or "materia_sin_nombre"


def merge_subject_dicts(base_subjects: Dict[str, Dict], global_subjects: Dict[str, Dict]) -> Dict[str, Dict]:
    """Combina diccionario base + global con prioridad del base por ID y nombre."""
    base_subjects = base_subjects or {}
    global_subjects = global_subjects or {}

    merged: Dict[str, Dict] = dict(global_subjects)
    merged.update(base_subjects)

    # Si hay colision por nombre oficial normalizado, mantener la entrada del base.
    base_names = {
        normalize_subject_name(v.get("nombre_oficial", ""))
        for v in base_subjects.values()
        if v.get("nombre_oficial")
    }
    for subject_id, data in list(merged.items()):
        if subject_id in base_subjects:
            continue
        nombre = normalize_subject_name(data.get("nombre_oficial", ""))
        if nombre and nombre in base_names:
            merged.pop(subject_id, None)

    return merged
