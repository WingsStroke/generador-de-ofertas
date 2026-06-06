import re
import unicodedata
from typing import Dict, Optional, List
from rapidfuzz import fuzz, process


# ── Patrones de ubicación ────────────────────────────────────────────────────
# Este patrón SOLO elimina identificadores de aula concretos (código adjunto):
#   SALA 201 · LAB A3 · AULA B · BLOQUE 5 → se eliminan
#   "Laboratorio de Física" · "Taller de Arte" → se CONSERVAN (no tienen código)
_STANDALONE_ROOM_PATTERN = re.compile(
    r'\b(?:AULA|LAB|SALA|SALON|SALÓN|EDIFICIO|BLOQUE|VIRTUAL)\s+[A-Z0-9][A-Z0-9]{0,4}\b',
    re.IGNORECASE,
)

_LOCATION_KEYWORDS = [
    'lab', 'laboratorio', 'sala', 'salón', 'salon', 'aula', 'edificio',
    'piso', 'bloque', 'taller', 'virtual', 'planta', 'grupo', 'grupos',
]

# ── Palabras de modalidad de curso ───────────────────────────────────────────
# Estas palabras describen el TIPO de clase (teórica vs. práctica) y aparecen
# frecuentemente al final del nombre en las celdas del horario de Alimentos.
# NO son parte del nombre oficial de la materia en el catálogo.
# Son usadas para:
#  a) Rechazarlas como posibles nombres de docente.
#  b) Limpiarlas del campo `aula` cuando van seguidas de un código de grupo.
_MODALITY_KEYWORDS = {
    'teoria', 'teoría', 'teorica', 'teórica',
    'laboratorio', 'laboratorio',
    'lab',
    'practica', 'práctica',
    'taller',
    'seminario',
    'virtual',
}

# ── Patrón de código de grupo ─────────────────────────────────────────────────
# Detecta códigos del tipo A1, F2, H1, E1, C1, etc.
# Una sola letra mayúscula seguida de uno o más dígitos.
_GROUP_CODE_RE = re.compile(r'^[A-Z]\d+$')


def looks_like_modality_group(text: str) -> bool:
    """Detecta si el texto consiste puramente de palabras de modalidad y/o códigos de grupo.
    Ejemplos: "Teoria A1", "Laboratorio F2", "Lab A3", "Teoría".
    """
    if not text:
        return False
    cleaned = re.sub(r'[.,;]', '', text).strip()
    words = cleaned.split()
    if not words:
        return False
    words_lower = [w.lower() for w in words]
    return all(
        w in _MODALITY_KEYWORDS or bool(_GROUP_CODE_RE.match(wup))
        for w, wup in zip(words_lower, words)
    )


def _ascii_key(s: str) -> str:
    """Normaliza a ASCII mayúsculas sin tildes ni puntos."""
    nfd = unicodedata.normalize('NFKD', s.upper().strip())
    no_acc = ''.join(c for c in nfd if not unicodedata.combining(c))
    return ' '.join(no_acc.replace('.', '').split())


def _remove_teacher_from_text(text: str, teacher_name: str, threshold: int = 85) -> str:
    """Elimina el nombre del docente del texto de la materia usando búsqueda
    por n-gramas de palabras contiguos. Preserva el resto del texto.

    Ejemplo:
        "Cálculo Diferencial Guillermo Muñoz Rodríguez", "Guillermo Muñoz Rodríguez"
        → "Cálculo Diferencial"
    """
    teacher_words = teacher_name.split()
    n = len(teacher_words)
    materia_words = text.split()

    if n == 0 or n > len(materia_words):
        return text

    teacher_key = _ascii_key(teacher_name)

    for i in range(len(materia_words) - n + 1):
        chunk = ' '.join(materia_words[i:i + n])
        chunk_key = _ascii_key(chunk)
        score = fuzz.token_sort_ratio(chunk_key, teacher_key)
        if score >= threshold:
            remaining = materia_words[:i] + materia_words[i + n:]
            result = ' '.join(remaining).strip()
            # Limpiar separadores sobrantes al inicio/fin
            result = re.sub(r'^[-–—,;\s]+|[-–—,;\s]+$', '', result).strip()
            return result if result else text

    return text


class SemanticParser:
    """Parser semántico para extraer entidades de texto de clases."""

    GRUPO_PATTERN = re.compile(r'\(?([A-Z]\d+)\)?')

    @staticmethod
    def extract_grupo(text: str) -> Optional[str]:
        """Extrae el grupo usando patrón [A-Z][0-9]+"""
        match = SemanticParser.GRUPO_PATTERN.search(text)
        return match.group(1) if match else None

    @staticmethod
    def extract_entities(text: str, teachers_list: List[str] = None) -> Dict[str, Optional[str]]:
        """Extrae materia, grupo, docente y aula de un texto."""
        if not text:
            return {
                "materia": None,
                "grupo": None,
                "docente": None,
                "origen_docente": "motor",
                "aula": None,
                "texto_limpio": "",
            }

        texto_limpio = text.strip()
        grupo = SemanticParser.extract_grupo(texto_limpio)

        parts = re.split(r'[-–—]', texto_limpio)
        parts = [p.strip() for p in parts if p.strip()]

        materia = None
        docente = None
        origen_docente = "motor"
        aula = None

        # ── Limpieza especial de la palabra "Aula" ───────────────────────────
        # A veces aparece "Aula Nombre Docente" o la palabra "Aula" pegada al final.
        for i in range(1, len(parts)):
            if re.match(r'(?i)^aula\s+[A-Z]', parts[i].strip()):
                parts[i] = re.sub(r'(?i)^aula\s+', '', parts[i].strip())


        # ── 1. Búsqueda de docente en diccionario con RapidFuzz ─────────────
        teachers_ascii = {}
        teachers_ascii_keys = []
        if teachers_list:
            teachers_ascii = {_ascii_key(t): t for t in teachers_list}
            teachers_ascii_keys = list(teachers_ascii.keys())

            for i, part in enumerate(parts):
                if len(part) > 5:
                    part_key = _ascii_key(part)
                    m = process.extractOne(
                        part_key, teachers_ascii_keys,
                        scorer=fuzz.token_sort_ratio, score_cutoff=83,
                    )
                    if m:
                        matched_teacher = teachers_ascii[m[0]]
                        if not looks_like_modality_group(matched_teacher):
                            docente = matched_teacher
                            origen_docente = "diccionario"

                            # Solo eliminar la parte si es PRINCIPALMENTE el nombre
                            # del docente (no un texto largo que contenga otros datos).
                            # Criterio: la parte no debe tener más del doble de palabras
                            # que el nombre del docente.
                            teacher_word_count = len(matched_teacher.split())
                            part_word_count = len(part.split())
                            if part_word_count <= teacher_word_count * 2:
                                parts.pop(i)
                            # Si la parte es más larga, NO se elimina — _clean_subject_name
                            # se encargará de quitar el nombre del docente de la materia.
                            break

            # Fallback: buscar en el texto completo con partial_ratio
            if not docente:
                text_key = _ascii_key(texto_limpio)
                m = process.extractOne(
                    text_key, teachers_ascii_keys,
                    scorer=fuzz.partial_ratio, score_cutoff=82,
                )
                if m:
                    matched_teacher = teachers_ascii[m[0]]
                    if not looks_like_modality_group(matched_teacher):
                        docente = matched_teacher
                        origen_docente = "diccionario"

        # ── 2. Extraer materia del primer fragmento ──────────────────────────
        if len(parts) >= 1:
            materia_raw = parts[0]
            if grupo:
                materia_raw = re.sub(SemanticParser.GRUPO_PATTERN, '', materia_raw).strip()
            materia = materia_raw

        # ── 3. Inferir docente y aula desde fragmentos restantes ────────────
        if len(parts) >= 2:
            # Limpiar "Aula" si quedó incrustada al inicio de la parte
            second_part_clean = re.sub(r'(?i)^aula\s+', '', parts[1]).strip()
            
            if not docente and SemanticParser._is_person_name(second_part_clean):
                docente = second_part_clean
                if len(parts) >= 3:
                    aula = parts[2]
            else:
                aula = parts[1]
                if len(parts) >= 3 and not docente:
                    third_part_clean = re.sub(r'(?i)^aula\s+', '', parts[2]).strip()
                    if SemanticParser._is_person_name(third_part_clean):
                        docente = third_part_clean

        if not docente and len(parts) >= 3:
            for part in parts[1:]:
                if SemanticParser._is_person_name(part):
                    docente = part
                    break

        if not aula and len(parts) >= 3:
            for part in reversed(parts[1:]):
                if not SemanticParser._is_person_name(part) and part != docente:
                    if any(kw in part.lower() for kw in ['lab', 'sal', 'aula', 'bloque', 'edificio']):
                        aula = part
                        break

        # ── 4. Verificador de nombre de materia ──────────────────────────────
        if materia:
            materia = SemanticParser._clean_subject_name(
                materia, docente, teachers_ascii, teachers_ascii_keys
            )

        # ── 5. Filtros de exclusión mutua para aula ─────────────────────────────────
        if aula and grupo:
            aula_limpia = re.sub(r'(?i)^grupo\s*', '', aula).strip()
            if aula_limpia == grupo:
                aula = None

        if aula and re.fullmatch(r'\(?[A-Z]\d+\)?', aula.strip()):
            if not any(kw in aula.lower() for kw in ['lab', 'sal', 'aula', 'bloque', 'edificio']):
                aula = None

        # 5b. Eliminar código de grupo residual al final del campo `aula`.
        # Caso frecuente en Alimentos: aula = "Laboratorio A1" cuando la celda es
        # "Quimica Organica Laboratorio A1". El grupo ya fue extraído; el aula debe
        # quedar como "Laboratorio" o eliminarse si es solo un código de grupo.
        if aula and grupo:
            # Quitar el código de grupo del final del campo aula
            aula_sin_grupo = re.sub(r'\s+' + re.escape(grupo) + r'\s*$', '', aula).strip()
            # Si aula queda vacía o es solo separador, limpiar
            aula_sin_grupo = re.sub(r'^[-\s]+$', '', aula_sin_grupo).strip()
            aula = aula_sin_grupo if aula_sin_grupo else None

        return {
            "materia": materia if materia else texto_limpio,
            "grupo": grupo,
            "docente": docente,
            "origen_docente": origen_docente,
            "aula": aula,
            "texto_limpio": texto_limpio,
        }

    @staticmethod
    def _clean_subject_name(
        materia: str,
        docente_encontrado: Optional[str],
        teachers_ascii: dict,
        teachers_ascii_keys: List[str],
    ) -> str:
        """Limpia el nombre de la materia eliminando docentes y aulas incrustados.

        Reglas:
        - Elimina el nombre del docente identificado usando n-gramas contiguos.
        - Elimina coincidencias de docentes del diccionario dentro del nombre.
        - Elimina solo identificadores de aula con código adjunto (SALA 201, LAB A3).
          NO elimina palabras como "Laboratorio" cuando son parte del nombre real.
        - Elimina códigos de grupo residuales al final.
        """
        cleaned = materia

        # 4a. Quitar el docente identificado por n-gramas contiguos
        if docente_encontrado:
            cleaned = _remove_teacher_from_text(cleaned, docente_encontrado, threshold=85)

        # 4b. Quitar otros docentes del diccionario que aparezcan en el nombre
        if teachers_ascii_keys and cleaned:
            # Buscar ventanas de 2, 3 y 4 palabras en el nombre de la materia
            words = cleaned.split()
            removed_ranges = []
            for n in (4, 3, 2):
                for i in range(len(words) - n + 1):
                    if any(i <= r < i + n for r in removed_ranges):
                        continue
                    chunk = ' '.join(words[i:i + n])
                    chunk_key = _ascii_key(chunk)
                    m = process.extractOne(
                        chunk_key, teachers_ascii_keys,
                        scorer=fuzz.token_sort_ratio, score_cutoff=88,
                    )
                    if m:
                        removed_ranges.extend(range(i, i + n))

            if removed_ranges:
                remaining = [w for idx, w in enumerate(words) if idx not in removed_ranges]
                cleaned = ' '.join(remaining).strip()

        # 4c. Quitar identificadores de aula CON código (SALA 201, LAB A3)
        # No toca "Laboratorio de Física" porque no va seguido de código corto.
        cleaned = _STANDALONE_ROOM_PATTERN.sub('', cleaned).strip()

        # 4d. Quitar código de grupo residual al final ("CALCULO III A1" → "CALCULO III")
        cleaned = re.sub(r'\s+[A-Z]\d+\s*$', '', cleaned).strip()

        # 4e. Quitar la palabra "Aula" si quedó pegada al final de la materia
        cleaned = re.sub(r'(?i)\s+aula\s*$', '', cleaned).strip()

        # 4f. Quitar palabras de modalidad de curso al final del nombre.
        # Las celdas del horario de Alimentos incluyen el tipo de clase al final:
        # "Fisica Mecanica Teoria"       → "Fisica Mecanica"
        # "Biologia Aplicada Laboratorio" → "Biologia Aplicada"
        # "Electromagnetismo Teoria"      → "Electromagnetismo"
        # "Quimica Organica Lab"          → "Quimica Organica"
        # IMPORTANTE: sólo se eliminan cuando están al FINAL del nombre y el
        # resultado no queda vacío (permite nombres de una sola palabra).
        modality_pattern = re.compile(
            r'(?i)\s+(?:teor[ií]a|te[oó]rica|laboratorio|lab|prá?ctica|seminario)\s*$'
        )
        stripped = modality_pattern.sub('', cleaned).strip()
        # Preservar si la materia es SOLO la palabra de modalidad (resultado vacío)
        # Nunca debe quedar vacío — si eso pasa, conservar el original.
        if stripped:
            cleaned = stripped


        # Limpiar separadores sobrantes
        cleaned = re.sub(r'^[-–—,;\s]+|[-–—,;\s]+$', '', cleaned).strip()

        return cleaned if cleaned else materia

    @staticmethod
    def _is_person_name(text: str) -> bool:
        """Heurística robusta para detectar si un texto es un nombre de persona.

        Reglas:
        - Acepta formato inicial + apellido: "J. PEREZ" o "J RAMIREZ".
        - Requiere al menos 2 palabras con mayúscula inicial.
        - Descarta palabras clave de ubicación física.
        - Descarta códigos alfanuméricos simples (ej. "A1", "LAB201").
        - Rechaza títulos de materia del tipo "CALCULO III" (1 no-romano + romano).
        - Rechaza fragmentos del tipo "Teoria A1", "Laboratorio F2"
          (modalidad de curso + código de grupo).
        """
        if not text:
            return False

        cleaned = re.sub(r'[.,;]', '', text).strip()
        words = cleaned.split()

        # Caso especial: inicial + apellido ("J PEREZ", "J. RAMIREZ")
        if (len(words) == 2
                and re.fullmatch(r'[A-Z]', words[0])
                and len(words[1]) > 3
                and words[1][0].isupper()):
            return True

        if len(words) < 2:
            return False

        caps = sum(1 for w in words if w and w[0].isupper())
        if caps < 2:
            return False

        lower = cleaned.lower()
        if any(kw in lower for kw in _LOCATION_KEYWORDS):
            return False

        if re.fullmatch(r'[A-Z]{1,4}\d+', cleaned):
            return False

        # Rechazar si TODAS las palabras son modalidades de curso o códigos de grupo.
        # Ejemplos problemáticos: "Teoria A1", "Laboratorio F2", "Lab A3".
        # Si todas las palabras caen en {modalidad} ∪ {código_grupo}, NO es persona.
        if looks_like_modality_group(text):
            return False

        # Rechazar si tiene número romano y solo 1 palabra no-romana
        # → "CALCULO III" = False, "GARCIA III" seguirá pasando (tiene apellido largo)
        roman_re = re.compile(r'^(?:I{1,3}|IV|VI{0,3}|IX|XI{0,3}|XIV|XV|XVI)$', re.IGNORECASE)
        has_roman = any(roman_re.match(w) for w in words)
        non_roman = [w for w in words if not roman_re.match(w)]
        if has_roman and len(non_roman) <= 1:
            return False

        return len(cleaned) > 5
