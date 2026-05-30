import re
from typing import List

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
        """Divide una celda que contiene múltiples clases.

        Mejoras respecto a la versión anterior:
        - Fusiona líneas que terminan con guión (word-wrap del PDF).
        - Si la celda sólo tiene un grupo en todas sus líneas, la trata
          como una única clase (evita partir incorrectamente celdas largas).
        """
        if not text:
            return []

        text = text.strip()
        text = re.sub(r'[ \t\f\v]+', ' ', text)  # normaliza espacios, conserva \n

        # ── Procesamiento de líneas con salto de párrafo ──────────────────────
        if '\n' in text:
            # Paso 1: fusionar líneas que terminan con guión (word-wrap del PDF)
            lines_raw = text.split('\n')
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

            group_pattern = re.compile(r'\b[A-Z]{1,2}\d+\b')

            # Contar cuántas líneas tienen grupo
            total_groups = sum(1 for line in lines if group_pattern.search(line))

            # Si hay ≤1 grupo en total, es una sola clase con texto largo → unir
            if total_groups <= 1:
                return [re.sub(r'\s+', ' ', ' '.join(lines))]

            first_has_group = bool(group_pattern.search(lines[0]))
            all_others_have_group = all(group_pattern.search(line) for line in lines[1:])

            if not first_has_group and all_others_have_group:
                subject = lines[0]
                return [f"{subject} - {line}" for line in lines[1:]]

            # Fusionar líneas sin grupo con la anterior (info extra: aula, etc.)
            merged_lines: List[str] = []
            for line in lines:
                if not merged_lines:
                    merged_lines.append(line)
                elif not group_pattern.search(line) or line.startswith('('):
                    merged_lines[-1] += f" {line}"
                else:
                    merged_lines.append(line)

            text = ' | '.join(merged_lines)

        # Convertir \n restantes a |
        text = text.replace('\n', ' | ')
        
        # Separadores tradicionales
        separators = ['|', '/', ';']
        for sep in separators:
            if sep in text:
                parts = [p.strip() for p in text.split(sep) if p.strip()]
                if len(parts) > 1:
                    return parts

        # Capa 1: Frontera de clases inline (guiones o espacios)
        # Ejemplo: "Materia1 - Grupo1 Materia2 - Grupo2"
        group_regex = re.compile(r'\b[A-Z]\d+\b')
        matches = list(group_regex.finditer(text))
        
        if len(matches) > 1:
            classes = []
            last_end = 0
            for i in range(len(matches)):
                start = matches[i].start()
                end = matches[i].end()
                
                if i < len(matches) - 1:
                    next_start = matches[i+1].start()
                    between_text = text[end:next_start].strip(' -_.,')
                    
                    # Si el texto intermedio parece una materia (letras y cierta longitud), es una frontera
                    if len(between_text) > 4 and re.search(r'[A-Za-z]', between_text):
                        classes.append(text[last_end:end].strip(' -_.,'))
                        last_end = end
                else:
                    classes.append(text[last_end:].strip(' -_.,'))
            
            if len(classes) > 1:
                return classes
        
        # Patron "(A1) (A2)"
        group_pattern_parens = re.compile(r'\([A-Z]\d+\)')
        matches_parens = list(group_pattern_parens.finditer(text))
        if len(matches_parens) > 1:
            classes = []
            for i, match in enumerate(matches_parens):
                start = match.start()
                if i == 0:
                    prev_text = text[:start].strip()
                    if prev_text:
                        classes.append(prev_text)
                
                if i < len(matches_parens) - 1:
                    end = matches_parens[i + 1].start()
                    classes.append(text[start:end].strip())
                else:
                    classes.append(text[start:].strip())
            
            return [c for c in classes if c]
        
        # Patron "A1, A2" o "A1 y A2"
        multiple_groups_pattern = re.compile(r'([A-Z]\d+)\s*[,yY&]\s*([A-Z]\d+)')
        if multiple_groups_pattern.search(text):
            grupos_encontrados = re.findall(r'[A-Z]\d+', text)
            if len(grupos_encontrados) > 1:
                base_text = multiple_groups_pattern.sub('', text).strip(' -_.,')
                if base_text:
                    classes = []
                    for grupo in grupos_encontrados:
                        class_text = f"{base_text} - {grupo}"
                        classes.append(class_text)
                    return classes
        
        return [text]
    
    @staticmethod
    def extract_multiple_groups(text: str) -> List[str]:
        """Extrae múltiples grupos de un texto como 'A1, A2' o 'A1 y A2'"""
        group_patterns = [
            re.compile(r'([A-Z]\d+)\s*,\s*([A-Z]\d+)'),
            re.compile(r'([A-Z]\d+)\s+y\s+([A-Z]\d+)'),
            re.compile(r'([A-Z]\d+)\s*&\s*([A-Z]\d+)'),
            re.compile(r'([A-Z]\d+)\s*/\s*([A-Z]\d+)')
        ]
        
        for pattern in group_patterns:
            if pattern.search(text):
                grupos = re.findall(r'[A-Z]\d+', text)
                if len(grupos) > 1:
                    return grupos
        
        return []
