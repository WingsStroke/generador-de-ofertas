from rapidfuzz import fuzz, process, utils
from typing import Dict, Optional, Tuple, List

class SubjectMatcher:
    """Realiza fuzzy matching de materias con el diccionario académico"""
    
    def __init__(self, subject_dict: Dict[str, Dict]):
        self.subject_dict = subject_dict
        self.subject_names = {v["nombre_oficial"]: k for k, v in subject_dict.items()}
        self.subject_list = list(self.subject_names.keys())
    
    def match_subject(self, text: str, threshold: int = 80) -> Tuple[Optional[str], Optional[str], float]:
        """Busca coincidencia de materia en el diccionario
        
        Returns:
            (subject_id, nombre_oficial, confidence)
        """
        if not text or not self.subject_list:
            return None, None, 0.0
        
        text_clean = text.strip()
        
        if text_clean.lower() in {k.lower() for k in self.subject_dict.keys()}:
            for key, value in self.subject_dict.items():
                if key.lower() == text_clean.lower():
                    return key, value["nombre_oficial"], 1.0
        
        for name in self.subject_list:
            if name.lower() == text_clean.lower():
                subject_id = self.subject_names[name]
                return subject_id, name, 1.0
        
        result = process.extractOne(
            text_clean,
            self.subject_list,
            scorer=fuzz.token_sort_ratio,
            processor=utils.default_process
        )
        
        if result and result[1] >= threshold:
            matched_name = result[0]
            subject_id = self.subject_names[matched_name]
            confidence = result[1] / 100.0
            return subject_id, matched_name, confidence
        
        return None, text_clean, 0.0
    
    def get_suggestions(self, text: str, limit: int = 5) -> List[Tuple[str, str, float]]:
        """Obtiene sugerencias de materias similares
        
        Returns:
            Lista de (subject_id, nombre_oficial, confidence)
        """
        if not text or not self.subject_list:
            return []
        
        results = process.extract(
            text.strip(),
            self.subject_list,
            scorer=fuzz.token_sort_ratio,
            processor=utils.default_process,
            limit=limit
        )
        
        suggestions = []
        for name, score, _ in results:
            subject_id = self.subject_names[name]
            suggestions.append((subject_id, name, score / 100.0))
        
        return suggestions
