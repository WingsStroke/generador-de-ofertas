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
        
        return [text]
