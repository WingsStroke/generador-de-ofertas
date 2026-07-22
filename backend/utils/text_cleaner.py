import re
from typing import List, Optional


# Patrón de grupo: una o dos letras mayúsculas seguidas de dígitos (A1, G1, F1, R1, etc.)
_GROUP_RE = re.compile(r'\b[A-Z]{1,2}\d+\b')

# Patrón de nombre de persona heurístico:
# - Todo en mayúsculas, al menos 2 palabras, puede terminar en "T." / "C." / "F." / "R." / "P." / "J."
# - O nombre + apellidos mixtos
_PERSON_NAME_RE = re.compile(
    r'^[A-ZÁÉÍÓÚÑ][a-záéíóúñA-ZÁÉÍÓÚÑ]+(?:\s+(?:de|del|la|las|los|De|Del|La))?'
    r'(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñA-ZÁÉÍÓÚÑ]+)+'
    r'(?:\s+[A-ZÁÉÍÓÚÑ]\.)?$',
    re.UNICODE
)

# Palabras que indican que la línea es un aula / ubicación física, no un docente
_LOCATION_WORDS = re.compile(
    r'\b(?:lab(?:oratorio)?|sal[oó]n|sala|aula|bloque|edificio|informática|simulaci[oó]n|'
    r'dibujo|geotecnia|materiales?|fisica|qu[ií]mica|biblioteca|virtual|taller)\b',
    re.IGNORECASE
)


def _is_person_line(line: str) -> bool:
    """
    Heurística robusta para decidir si una línea es un nombre de docente.

    Acepta:
      - "JORGE PEREZ"
      - "EDGAR MARIN T."          (inicial de apellido al final)
      - "PEDRO CAÑATE C."
      - "Jose Hernández Miranda"  (mixto)
      - "WALBERTO RIVERA"
      - "RAÚL CASTRO C."
    Rechaza:
      - "Salón de Dibujo"         (ubicación)
      - "Lab de Fisica"           (ubicación)
      - "Sala de Informática"     (ubicación)
      - "Grupo A1"                (grupo)
      - "GIMA GIMTH"              (acrónimos institucionales)
    """
    s = line.strip().rstrip('.')
    if not s or len(s) < 4:
        return False

    # Rechazar si contiene palabra de ubicación
    if _LOCATION_WORDS.search(s):
        return False

    # Rechazar si empieza con "Grupo" (aun en mayúsculas)
    if re.match(r'(?i)^grupo\b', s):
        return False

    # Rechazar parentéticos institucionales: "(ESCONPAT)", "(GIMA - GIHMAC)"
    if re.match(r'^\(', s):
        return False

    words = s.split()

    # Rechazar si es solo un acrónimo (todas mayúsculas, ≤ 2 palabras, sin vocal minúscula)
    if len(words) <= 2 and all(w.isupper() and len(w) <= 6 for w in words):
        # Podría ser una sigla institucional, no un nombre
        # Pero "JORGE PEREZ" también sería esto → solo rechazar si las palabras son muy cortas
        if all(len(w) <= 4 for w in words):
            return False

    # Al menos 2 tokens y la primera letra de cada uno es mayúscula
    caps = sum(1 for w in words if w and (w[0].isupper() or w[0] in 'ÁÉÍÓÚ'))
    if caps < 2:
        return False

    # No debe ser solo números / códigos alfanuméricos
    if re.fullmatch(r'[A-Z]{1,4}\d+', s):
        return False

    # Si tiene número romano y solo 1 palabra no-romana → materia, no persona
    roman_re = re.compile(r'^(?:I{1,3}|IV|VI{0,3}|IX|XI{0,3}|XIV|XV|XVI)$', re.IGNORECASE)
    non_roman = [w for w in words if not roman_re.match(w)]
    if len(non_roman) <= 1 and any(roman_re.match(w) for w in words):
        return False

    return True


class TextCleaner:
    """Limpia y divide el texto de las celdas"""

    @staticmethod
    def clean_text(text: str) -> str:
        """Limpia espacios y caracteres innecesarios"""
        if not text:
            return ""
        text = text.strip()
        text = re.sub(r'[ \t\f\v]+', ' ', text)
        return text

    @staticmethod
    def split_multiple_classes(text: str) -> List[str]:
        """
        Divide una celda que puede contener múltiples clases.

        Formato típico de Ingeniería Civil (y otras):

            Cálculo Diferencial Grupo F1
            JORGE PEREZ
            Expresión Gráfica Grupo A1
            EDGAR MARIN T.
            Salón de Dibujo

        Estrategia:
          1. Fusiona word-wrap de guión.
          2. Detecta fronteras de clase: una línea que tiene código de grupo Y
             la anterior NO tenía código de grupo (es el nombre de la materia).
          3. Agrega el docente (línea inmediatamente posterior sin grupo y con
             aspecto de nombre de persona) y el aula (línea posterior sin grupo
             ni aspecto de nombre) como partes del mismo bloque, separadas con ' - '.
          4. Si la celda tiene ≤1 grupo total, trata todo como una sola clase
             usando la misma lógica de pegado docente/aula.
        """
        if not text:
            return []

        text = text.strip()
        text = re.sub(r'[ \t\f\v]+', ' ', text)  # normaliza espacios horizontales

        # ── Pre-inserción de separadores explícitos ──────────────────────────
        text = re.sub(r'(?i)[ \t\n]+(aula[ \t\n]+[A-ZÁÉÍÓÚÑ])', r' - \1', text)
        text = re.sub(r'(?i)[ \t\n]+(grupo\s+[A-Z0-9]+)\b', r' - \1', text)

        # ── Procesamiento con saltos de línea ────────────────────────────────
        if '\n' in text:
            lines_raw = text.split('\n')

            # Paso 1: fusionar word-wrap de guión
            lines: List[str] = []
            i = 0
            while i < len(lines_raw):
                line = lines_raw[i].strip()
                while line.endswith(('-', '\u2013', '\u2014')) and i + 1 < len(lines_raw):
                    next_line = lines_raw[i + 1].strip()
                    line = re.sub(r'\s*[-\u2013\u2014]\s*$', ' - ', line) + next_line
                    i += 1
                if line:
                    lines.append(line)
                i += 1

            if not lines:
                return [text]
            if len(lines) == 1:
                return [re.sub(r'\s+', ' ', lines[0])]

            # Paso 2: agrupar líneas en bloques de clase
            # Un bloque empieza cuando una línea contiene un código de grupo.
            # Las líneas siguientes sin grupo se anexan al bloque como
            # docente o aula según heurística.
            total_groups = sum(1 for l in lines if _GROUP_RE.search(l))

            if total_groups == 0:
                # Sin ningún grupo: unir todo como una clase
                return [re.sub(r'\s+', ' ', ' '.join(lines))]

            # ── Caso especial: primera línea = nombre de materia, el resto
            # tiene grupos (patrón "nombre arriba, grupos abajo")
            first_has_group = bool(_GROUP_RE.search(lines[0]))
            all_others_have_group = all(_GROUP_RE.search(l) for l in lines[1:])
            if not first_has_group and all_others_have_group:
                subject = lines[0]
                return [re.sub(r'\s+', ' ', f"{subject} - {line}") for line in lines[1:]]

            # ── Caso general: agrupar secuencialmente ────────────────────────
            # Cada línea con grupo inicia un nuevo bloque.
            # Las líneas sin grupo que vienen después pertenecen al bloque anterior.
            # Si la primera línea no tiene grupo, es el nombre de materia compartido.
            shared_subject: Optional[str] = None
            if not first_has_group:
                shared_subject = lines[0]
                lines = lines[1:]

            blocks: List[List[str]] = []  # cada sub-lista: [línea_con_grupo, extra1, extra2…]
            for line in lines:
                if _GROUP_RE.search(line):
                    if shared_subject:
                        blocks.append([f"{shared_subject} {line}"])
                    else:
                        blocks.append([line])
                else:
                    if blocks:
                        blocks[-1].append(line)
                    # else: línea antes del primer grupo (no debería ocurrir aquí)

            if not blocks:
                return [re.sub(r'\s+', ' ', ' '.join(lines))]

            # Paso 3: para cada bloque, separar docente y aula con ' - '
            result = []
            for block_lines in blocks:
                parts = [block_lines[0]]  # primera línea: materia + grupo
                for extra in block_lines[1:]:
                    extra_s = extra.strip()
                    if not extra_s:
                        continue
                    # Anexar con ' - ' para que SemanticParser los vea como fragmentos
                    parts.append(extra_s)
                combined = ' - '.join(parts)
                combined = re.sub(r'\s+', ' ', combined)
                result.append(combined)

            return result if result else [re.sub(r'\s+', ' ', text)]

        # ── Sin saltos de línea: flujo original ──────────────────────────────
        text = text.replace('\n', ' | ')

        separators = ['|', '/', ';']
        for sep in separators:
            if sep in text:
                parts = [p.strip() for p in text.split(sep) if p.strip()]
                if len(parts) > 1:
                    return parts

        # Capa 1: Frontera de clases inline (guiones o espacios entre grupos)
        matches = list(_GROUP_RE.finditer(text))
        if len(matches) > 1:
            classes = []
            last_end = 0
            for i in range(len(matches)):
                end = matches[i].end()
                if i < len(matches) - 1:
                    next_start = matches[i + 1].start()
                    between_text = text[end:next_start].strip(' -_.,')
                    if len(between_text) > 4 and re.search(r'[A-Za-z]', between_text):
                        classes.append(text[last_end:end].strip(' -_.,'))
                        last_end = end
                else:
                    classes.append(text[last_end:].strip(' -_.,'))
            if len(classes) > 1:
                return classes

        # Patrón "(A1) (A2)"
        matches_parens = list(re.compile(r'\([A-Z]\d+\)').finditer(text))
        if len(matches_parens) > 1:
            classes = []
            for i, match in enumerate(matches_parens):
                start = match.start()
                if i == 0:
                    prev_text = text[:start].strip()
                    if prev_text:
                        classes.append(prev_text)
                end_next = matches_parens[i + 1].start() if i < len(matches_parens) - 1 else len(text)
                classes.append(text[start:end_next].strip())
            return [c for c in classes if c]

        # Patrón "A1, A2" o "A1 y A2"
        multiple_groups_pattern = re.compile(r'([A-Z]\d+)\s*[,yY&]\s*([A-Z]\d+)')
        if multiple_groups_pattern.search(text):
            grupos_encontrados = re.findall(r'[A-Z]\d+', text)
            if len(grupos_encontrados) > 1:
                base_text = multiple_groups_pattern.sub('', text).strip(' -_.,')
                if base_text:
                    return [f"{base_text} - {g}" for g in grupos_encontrados]

        return [text]

    @staticmethod
    def extract_multiple_groups(text: str) -> List[str]:
        """Extrae múltiples grupos de un texto como 'A1, A2' o 'A1 y A2'"""
        patterns = [
            re.compile(r'([A-Z]\d+)\s*,\s*([A-Z]\d+)'),
            re.compile(r'([A-Z]\d+)\s+y\s+([A-Z]\d+)'),
            re.compile(r'([A-Z]\d+)\s*&\s*([A-Z]\d+)'),
            re.compile(r'([A-Z]\d+)\s*/\s*([A-Z]\d+)'),
        ]
        for pattern in patterns:
            if pattern.search(text):
                grupos = re.findall(r'[A-Z]\d+', text)
                if len(grupos) > 1:
                    return grupos
        return []
