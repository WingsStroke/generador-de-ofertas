import json
import logging
import unicodedata
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class TeachersStorage:
    """
    Almacenamiento del diccionario de docentes con deduplicación robusta.

    Internamente usa un dict {ascii_key → nombre_display} donde:
    - ascii_key: nombre sin tildes, sin puntos, en mayúsculas, espacios normalizados.
      Esto garantiza que "YAZMÍN" y "YAZMIN" sean la misma clave.
    - nombre_display: la versión completa y acentuada para mostrar al usuario.

    El formato en disco sigue siendo {'teachers': [lista de strings]} para
    retrocompatibilidad.
    """

    def __init__(self, data_file: str = './data/teachers.json'):
        self.data_file = Path(data_file)
        # Dict: ascii_key → display_name
        self._teachers: Dict[str, str] = {}
        self._last_mtime = 0.0
        self._load()

    def _check_reload(self):
        """Sincroniza la memoria si el archivo fue modificado por otro worker."""
        try:
            if self.data_file.exists():
                mtime = self.data_file.stat().st_mtime
                if mtime > self._last_mtime:
                    self._load()
        except Exception as e:
            logger.warning(f"No se pudo comprobar reload de docentes: {e}")

    # ─────────────────────────────────────────────────────────
    # Núcleo de normalización
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _ascii_key(name: str) -> str:
        """
        Clave de identidad canónica:
        1. Mayúsculas
        2. NFKD descompone caracteres compuestos (Á → A + acento)
        3. Se eliminan todos los caracteres combining (acentos, diéresis, etc.)
        4. Se eliminan puntos (para tratar 'M.' igual que 'M')
        5. Espacios colapsados
        """
        upper = name.upper().strip()
        nfd = unicodedata.normalize('NFKD', upper)
        no_accents = ''.join(c for c in nfd if not unicodedata.combining(c))
        no_dots = no_accents.replace('.', '')
        return ' '.join(no_dots.split())

    @staticmethod
    def _display_normalize(name: str) -> str:
        """Normalización para display: NFC (formas compuestas), mayúsculas, espacios."""
        upper = ' '.join(name.strip().upper().split())
        return unicodedata.normalize('NFC', upper)

    # ─────────────────────────────────────────────────────────
    # Persistencia
    # ─────────────────────────────────────────────────────────

    def _load(self):
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                raw_list = data.get('teachers', [])

                # Reconstruir el dict con deduplicación automática:
                # Si dos nombres tienen la misma clave ASCII, ganará el más largo
                # (nombre completo > nombre abreviado).
                new_store: Dict[str, str] = {}
                for name in raw_list:
                    if not name or not name.strip():
                        continue
                    display = self._display_normalize(name)
                    key = self._ascii_key(display)
                    if key not in new_store:
                        new_store[key] = display
                    else:
                        # Preferir el nombre más largo (más completo)
                        if len(display) > len(new_store[key]):
                            new_store[key] = display

                if len(new_store) < len(raw_list):
                    logger.info(
                        f"Deduplicación automática al cargar: "
                        f"{len(raw_list)} → {len(new_store)} docentes"
                    )

                self._teachers = new_store
                self._last_mtime = self.data_file.stat().st_mtime
                # Si hubo deduplicación, persistir inmediatamente
                if len(new_store) < len(raw_list):
                    self._save()

            except Exception as e:
                logger.error(f"Error loading teachers: {e}")
        else:
            self.data_file.parent.mkdir(parents=True, exist_ok=True)
            self._save()

    def _save(self):
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(
                    {'teachers': sorted(self._teachers.values())},
                    f, indent=2, ensure_ascii=False
                )
            self._last_mtime = self.data_file.stat().st_mtime
        except Exception as e:
            logger.error(f"Error saving teachers: {e}")

    # ─────────────────────────────────────────────────────────
    # Detección de abreviaciones
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _is_abbreviation_match(name_a_ascii: str, name_b_ascii: str) -> bool:
        """
        Detecta si un nombre es abreviación del otro.
        Lógica: todas las palabras del nombre más corto deben:
          - Ser iguales a la palabra correspondiente del nombre más largo, O
          - Ser una inicial de 1 letra que coincide con el primer carácter de
            la palabra correspondiente más larga.

        Ejemplos:
          'RANDY ZABALETA M' ≈ 'RANDY ZABALETA MESINO'  → True  (M = inicial de MESINO)
          'JUAN GARCIA M'    ≈ 'JUAN GARCIA MARTINEZ'    → True
          'J GARCIA'         ≈ 'JUAN GARCIA MARTINEZ'    → True  (J = inicial de JUAN)
          'PEDRO LOPEZ'      ≈ 'PEDRO RAMIREZ'           → False (apellidos distintos)
        """
        words_a = name_a_ascii.split()
        words_b = name_b_ascii.split()

        # La abreviación tiene ≤ palabras que el nombre completo
        if len(words_a) > len(words_b):
            words_a, words_b = words_b, words_a

        # Recorrer en paralelo desde el inicio
        for wa, wb in zip(words_a, words_b):
            if wa == wb:
                continue
            # ¿wa es la inicial de wb?
            if len(wa) == 1 and wb.startswith(wa):
                continue
            # ¿wb es la inicial de wa? (raro pero posible)
            if len(wb) == 1 and wa.startswith(wb):
                continue
            return False
        return True

    # ─────────────────────────────────────────────────────────
    # Búsqueda de similares
    # ─────────────────────────────────────────────────────────

    def find_similar(self, name: str, threshold: int = 82) -> List[Tuple[str, int]]:
        """
        Busca docentes similares en el diccionario usando dos estrategias:

        1. Abreviación exacta: si name_a es abreviación de name_b → score 95
        2. Fuzzy token_sort_ratio en claves ASCII: compara sin tildes y sin puntos

        Retorna lista de (display_name, score) ordenada de mayor a menor score,
        excluyendo coincidencias exactas (ascii_key idéntico).
        """
        self._check_reload()
        try:
            from rapidfuzz import fuzz, process
        except ImportError:
            return []

        if not name or not self._teachers:
            return []

        display_in = self._display_normalize(name)
        key_in = self._ascii_key(display_in)

        # Excluir coincidencia exacta (ya existe)
        candidates = {k: v for k, v in self._teachers.items() if k != key_in}
        if not candidates:
            return []

        results: Dict[str, int] = {}

        # Estrategia 1: Detección de abreviaciones (prioridad alta)
        for key, display in candidates.items():
            if self._is_abbreviation_match(key_in, key):
                results[display] = max(results.get(display, 0), 95)

        # Estrategia 2: Fuzzy sobre claves ASCII (sin tildes, sin puntos)
        candidate_keys = list(candidates.keys())
        candidate_displays = list(candidates.values())

        fuzzy_results = process.extract(
            key_in,
            candidate_keys,
            scorer=fuzz.token_sort_ratio,
            limit=5
        )
        for match_key, score, idx in fuzzy_results:
            if score >= threshold:
                display = candidate_displays[idx]
                results[display] = max(results.get(display, 0), score)

        return sorted(results.items(), key=lambda x: x[1], reverse=True)

    # ─────────────────────────────────────────────────────────
    # CRUD
    # ─────────────────────────────────────────────────────────

    def get_all(self) -> List[str]:
        self._check_reload()
        return sorted(self._teachers.values())

    def add(self, name: str, force: bool = False) -> dict:
        self._check_reload()
        """
        Añade un docente con verificación de duplicados.
        - Si la clave ASCII ya existe: retorna added=False (ya existe).
        - Si hay similares y force=False: retorna requires_confirmation=True.
        - Si force=True o no hay similares: añade.
        """
        display = self._display_normalize(name)
        key = self._ascii_key(display)

        if not key:
            return {"added": False, "normalized": "", "requires_confirmation": False, "similar": []}

        if key in self._teachers:
            return {
                "added": False,
                "normalized": self._teachers[key],
                "requires_confirmation": False,
                "similar": []
            }

        if not force:
            similar = self.find_similar(display)
            if similar:
                return {
                    "added": False,
                    "normalized": display,
                    "requires_confirmation": True,
                    "similar": similar
                }

        self._teachers[key] = display
        self._save()
        return {"added": True, "normalized": display, "requires_confirmation": False, "similar": []}

    def add_multiple(self, names: List[str]) -> int:
        self._check_reload()
        """Añade múltiples docentes sin verificación fuzzy (extracción masiva)."""
        added = 0
        for name in names:
            display = self._display_normalize(name)
            key = self._ascii_key(display)
            if key and key not in self._teachers:
                self._teachers[key] = display
                added += 1
        if added > 0:
            self._save()
        return added

    def remove(self, name: str) -> bool:
        self._check_reload()
        """Elimina un docente. Idempotente: retorna False si no existía."""
        key = self._ascii_key(name.upper().strip())
        if key in self._teachers:
            del self._teachers[key]
            self._save()
            return True
        return False

    def replace(self, old_name: str, new_name: str) -> bool:
        self._check_reload()
        """Reemplaza un nombre (fusión de duplicados)."""
        old_key = self._ascii_key(old_name.upper().strip())
        new_display = self._display_normalize(new_name)
        new_key = self._ascii_key(new_display)
        if not old_key or not new_key:
            return False
        self._teachers.pop(old_key, None)
        self._teachers[new_key] = new_display
        self._save()
        return True


# Singleton
teachers_storage = TeachersStorage()
