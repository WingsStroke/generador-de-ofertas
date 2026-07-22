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
        """Extrae materia, grupo, docente y aula de un texto.

        El TextCleaner ya convirtió los saltos de línea del patrón Civil en ' - ',
        por lo que recibimos texto como:
          "Cálculo Diferencial Grupo F1 - JORGE PEREZ"
          "Expresión Gráfica Grupo A1 - EDGAR MARIN T. - Salón de Dibujo"
          "Diseño Asistido Grupo A1 - Sala de Simulación - EDGAR MARIN."
        """
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
                            teacher_word_count = len(matched_teacher.split())
                            part_word_count = len(part.split())
                            if part_word_count <= teacher_word_count * 2:
                                parts.pop(i)
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

        # ── 3. Asignar docente y aula de los fragmentos restantes ───────────
        # Recorremos parts[1:] y clasificamos cada fragmento:
        #   - Si parece nombre de persona → docente (primera vez)
        #   - Si parece ubicación → aula (primera vez)
        # El orden puede ser cualquiera (Civil pone docente antes o después del aula).
        remaining = parts[1:] if len(parts) > 1 else []

        for part in remaining:
            part_clean = re.sub(r'(?i)^aula\s+', '', part).strip()
            if not part_clean:
                continue

            is_person = SemanticParser._is_person_name(part_clean)
            is_location = bool(
                re.search(
                    r'(?i)\b(?:lab(?:oratorio)?|sal[oó]n|sala|aula|bloque|edificio|'
                    r'informática|simulaci[oó]n|dibujo|geotecnia|materiales?|f[ií]sica|'
                    r'qu[ií]mica|biblioteca|virtual|taller)\b',
                    part_clean
                )
            )

            if is_person and not docente:
                # Verificar que no sea una modalidad
                if not looks_like_modality_group(part_clean):
                    docente = part_clean
                    origen_docente = "motor"
            elif is_location and not aula:
                aula = part_clean
            elif not is_person and not is_location and not docente:
                # Fragmento ambiguo: intentar heurística _is_person_name
                if SemanticParser._is_person_name(part_clean):
                    docente = part_clean
                    origen_docente = "motor"

        # ── 4. Fallback: si solo hay 2 partes y la segunda parece persona ────
        if not docente and len(parts) == 2:
            second = parts[1]
            second_clean = re.sub(r'(?i)^aula\s+', '', second).strip()
            if SemanticParser._is_person_name(second_clean) and not looks_like_modality_group(second_clean):
                docente = second_clean
                origen_docente = "motor"

        # ── 5. Verificador de nombre de materia ──────────────────────────────
        if materia:
            materia = SemanticParser._clean_subject_name(
                materia, docente, teachers_ascii, teachers_ascii_keys
            )

        # ── 6. Filtros de exclusión mutua para aula ──────────────────────────
        if aula and grupo:
            aula_limpia = re.sub(r'(?i)^grupo\s*', '', aula).strip()
            if aula_limpia == grupo:
                aula = None

        if aula and re.fullmatch(r'\(?[A-Z]\d+\)?', aula.strip()):
            if not any(kw in aula.lower() for kw in ['lab', 'sal', 'aula', 'bloque', 'edificio']):
                aula = None

        if aula and grupo:
            aula_sin_grupo = re.sub(r'\s+' + re.escape(grupo) + r'\s*$', '', aula).strip()
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

        # 4d2. Quitar la palabra "Grupo" si quedó residual al final del nombre.
        # Ocurre cuando la celda tiene "Cálculo Diferencial Grupo F1" y el grupo
        # (F1) ya fue extraído: queda "Cálculo Diferencial Grupo" → limpiar "Grupo".
        cleaned = re.sub(r'(?i)\s+grupo\s*$', '', cleaned).strip()

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

        Acepta:
          - "JORGE PEREZ", "EDGAR MARIN T.", "PEDRO CAÑATE C."  (apellido con inicial)
          - "Jose Hernández Miranda", "RAÚL CASTRO C."
          - "J. PEREZ", "J RAMIREZ"  (inicial + apellido)
        Rechaza:
          - Palabras de ubicación (Lab, Salón, Sala, Aula, Bloque…)
          - Códigos de grupo (A1, G1…)
          - Modalidades de curso (Teoría, Laboratorio…)
          - Siglas institucionales cortas (GIMA, SIG…)
          - Números romanos solos ("Cálculo III")
        """
        if not text:
            return False

        cleaned = re.sub(r'[.,;]', '', text).strip()
        if not cleaned or len(cleaned) < 4:
            return False

        # Rechazar si contiene palabra de ubicación
        if any(kw in cleaned.lower() for kw in _LOCATION_KEYWORDS):
            return False

        # Rechazar modalidades de curso
        if looks_like_modality_group(cleaned):
            return False

        # Rechazar paréntesis institucional  "(ESCONPAT)", "(GIMA)"
        if cleaned.startswith('('):
            return False

        # Rechazar si empieza con "Grupo"
        if re.match(r'(?i)^grupo\b', cleaned):
            return False

        words = cleaned.split()

        # Caso especial: inicial + apellido ("J PEREZ", "J. RAMIREZ")
        if (len(words) == 2
                and re.fullmatch(r'[A-ZÁÉÍÓÚÑ]', words[0])
                and len(words[1]) > 3
                and words[1][0].isupper()):
            return True

        if len(words) < 2:
            return False

        # Caso: "NOMBRE APELLIDO T."  — la última palabra es una inicial (una letra)
        # Validar igualmente: el resto debe parecer un nombre
        last_word = words[-1]
        effective_words = words[:-1] if re.fullmatch(r'[A-ZÁÉÍÓÚÑ]', last_word) else words

        caps = sum(1 for w in effective_words if w and (w[0].isupper() or w[0] in 'ÁÉÍÓÚ'))
        if caps < 2:
            return False

        # Rechazar si todas las palabras son siglas muy cortas (≤3 chars, todo mayúsculas).
        # Casos: "SIG CAD", "GIS VIA" → no son nombres de persona.
        # "EDIL MELO", "EDIL MELO J" → NO se rechazan (al menos una tiene >3 letras).
        if all(w.isupper() and len(w) <= 3 for w in effective_words):
            return False

        # Código alfanumérico puro
        if re.fullmatch(r'[A-Z]{1,4}\d+', cleaned):
            return False

        # Rechazar si tiene número romano y solo 1 palabra no-romana ("CALCULO III")
        roman_re = re.compile(r'^(?:I{1,3}|IV|VI{0,3}|IX|XI{0,3}|XIV|XV|XVI)$', re.IGNORECASE)
        has_roman = any(roman_re.match(w) for w in words)
        non_roman = [w for w in words if not roman_re.match(w)]
        if has_roman and len(non_roman) <= 1:
            return False

        return len(cleaned) > 5
