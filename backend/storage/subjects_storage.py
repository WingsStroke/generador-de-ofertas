import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from utils.subject_utils import derive_subject_id

logger = logging.getLogger(__name__)


class SubjectsStorage:
    """Diccionario global de asignaturas persistido en JSON."""

    def __init__(self, data_file: str = "./data/subjects.json"):
        self.data_file = Path(data_file)
        self._subjects: Dict[str, Dict] = {}
        self._last_mtime = 0.0
        self._load()

    def _check_reload(self):
        try:
            if self.data_file.exists():
                mtime = self.data_file.stat().st_mtime
                if mtime > self._last_mtime:
                    self._load()
        except Exception as e:
            logger.warning(f"No se pudo recargar subjects.json: {e}")

    def _load(self):
        if self.data_file.exists():
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                loaded: Dict[str, Dict] = {}
                for item in data.get("subjects", []):
                    if not isinstance(item, dict):
                        continue
                    nombre = str(item.get("nombre_oficial", "")).strip()
                    if not nombre:
                        continue
                    subject_id = str(item.get("id") or derive_subject_id(nombre)).strip()
                    loaded[subject_id] = {
                        "id": subject_id,
                        "nombre_oficial": nombre,
                        "codigo": item.get("codigo"),
                        "creditos": item.get("creditos"),
                    }
                self._subjects = loaded
                self._last_mtime = self.data_file.stat().st_mtime
            except Exception as e:
                logger.error(f"Error cargando subjects globales: {e}")
        else:
            self.data_file.parent.mkdir(parents=True, exist_ok=True)
            self._save()

    def _save(self):
        try:
            payload = {
                "subjects": sorted(self._subjects.values(), key=lambda x: x.get("nombre_oficial", ""))
            }
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            self._last_mtime = self.data_file.stat().st_mtime
        except Exception as e:
            logger.error(f"Error guardando subjects globales: {e}")

    def get_all(self) -> List[Dict]:
        self._check_reload()
        return sorted(self._subjects.values(), key=lambda x: x.get("nombre_oficial", ""))

    def get_all_dict(self) -> Dict[str, Dict]:
        self._check_reload()
        return {k: dict(v) for k, v in self._subjects.items()}

    def get(self, subject_id: str) -> Optional[Dict]:
        self._check_reload()
        if subject_id in self._subjects:
            return dict(self._subjects[subject_id])
        return None

    def upsert(self, subject_id: Optional[str], nombre_oficial: str, codigo=None, creditos=None) -> Dict:
        self._check_reload()
        nombre = (nombre_oficial or "").strip()
        if not nombre:
            raise ValueError("nombre_oficial es requerido")

        normalized_id = (subject_id or "").strip() or derive_subject_id(nombre)

        subject = {
            "id": normalized_id,
            "nombre_oficial": nombre,
            "codigo": codigo,
            "creditos": creditos,
        }
        self._subjects[normalized_id] = subject
        self._save()
        return dict(subject)

    def delete(self, subject_id: str) -> bool:
        self._check_reload()
        if subject_id in self._subjects:
            del self._subjects[subject_id]
            self._save()
            return True
        return False


subjects_storage = SubjectsStorage()
