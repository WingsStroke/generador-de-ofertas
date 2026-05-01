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
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[\n\r]+', ' | ', text)
        
        return text
    
    @staticmethod
    def split_multiple_classes(text: str) -> List[str]:
        """Divide una celda que contiene múltiples clases"""
        if not text:
            return []
        
        text = TextCleaner.clean_text(text)
        
        separators = ['|', '\n', '\r', '/', ';']
        for sep in separators:
            if sep in text:
                parts = [p.strip() for p in text.split(sep) if p.strip()]
                if len(parts) > 1:
                    return parts
        
        group_pattern = re.compile(r'\([A-Z]\d+\)')
        matches = list(group_pattern.finditer(text))
        
        if len(matches) > 1:
            classes = []
            for i, match in enumerate(matches):
                start = match.start()
                if i == 0:
                    prev_text = text[:start].strip()
                    if prev_text:
                        classes.append(prev_text)
                
                if i < len(matches) - 1:
                    end = matches[i + 1].start()
                    classes.append(text[start:end].strip())
                else:
                    classes.append(text[start:].strip())
            
            return [c for c in classes if c]
        
        multiple_groups_pattern = re.compile(r'([A-Z]\d+)\s*[,yY&]\s*([A-Z]\d+)')
        if multiple_groups_pattern.search(text):
            grupos_encontrados = re.findall(r'[A-Z]\d+', text)
            if len(grupos_encontrados) > 1:
                base_text = multiple_groups_pattern.sub('', text).strip()
                if base_text:
                    classes = []
                    for grupo in grupos_encontrados:
                        class_text = f"{base_text} ({grupo})"
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
