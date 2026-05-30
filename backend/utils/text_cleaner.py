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
        """Divide una celda que contiene múltiples clases"""
        if not text:
            return []
        
        text = text.strip()
        text = re.sub(r'[ \t\f\v]+', ' ', text) # normalize spaces but KEEP \n if it exists
        
        # Capa 2: Propagación de materia por newline
        # Ejemplo: "Materia \n Grupo1 Docente \n Grupo2 Docente"
        if '\n' in text:
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            if len(lines) > 1:
                group_pattern = re.compile(r'\b[A-Z]{1,2}\d+\b')
                
                first_has_group = bool(group_pattern.search(lines[0]))
                all_others_have_group = all(group_pattern.search(line) for line in lines[1:])
                
                if not first_has_group and all_others_have_group:
                    subject = lines[0]
                    resolved_classes = []
                    for line in lines[1:]:
                        resolved_classes.append(f"{subject} - {line}")
                    return resolved_classes
                
                # Merge lines that are just extra info (e.g. classrooms in parentheses)
                merged_lines = []
                for line in lines:
                    if not merged_lines:
                        merged_lines.append(line)
                    else:
                        # Si la línea actual no tiene grupo, o empieza por '(', suele ser info del bloque anterior
                        if not group_pattern.search(line) or line.startswith('('):
                            merged_lines[-1] += f" {line}"
                        else:
                            merged_lines.append(line)
                            
                text = ' | '.join(merged_lines)

        # Convert remaining \n to | si existen
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
