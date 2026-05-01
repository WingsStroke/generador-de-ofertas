import re
from typing import Dict, Optional, Tuple

class SemanticParser:
    """Parser semántico para extraer entidades de texto de clases"""
    
    GRUPO_PATTERN = re.compile(r'\(?([A-Z]\d+)\)?')
    
    @staticmethod
    def extract_grupo(text: str) -> Optional[str]:
        """Extrae el grupo usando patrón [A-Z][0-9]+"""
        match = SemanticParser.GRUPO_PATTERN.search(text)
        return match.group(1) if match else None
    
    @staticmethod
    def extract_entities(text: str) -> Dict[str, Optional[str]]:
        """Extrae materia, grupo, docente y aula de un texto"""
        if not text:
            return {
                "materia": None,
                "grupo": None,
                "docente": None,
                "aula": None,
                "texto_limpio": ""
            }
        
        texto_limpio = text.strip()
        grupo = SemanticParser.extract_grupo(texto_limpio)
        
        parts = re.split(r'[-–—]', texto_limpio)
        parts = [p.strip() for p in parts if p.strip()]
        
        materia = None
        docente = None
        aula = None
        
        if len(parts) >= 1:
            materia_raw = parts[0]
            if grupo:
                materia_raw = re.sub(SemanticParser.GRUPO_PATTERN, '', materia_raw).strip()
            materia = materia_raw
        
        if len(parts) >= 2:
            second_part = parts[1]
            if SemanticParser._is_person_name(second_part):
                docente = second_part
                if len(parts) >= 3:
                    aula = parts[2]
            else:
                aula = second_part
                if len(parts) >= 3 and SemanticParser._is_person_name(parts[2]):
                    docente = parts[2]
        
        if len(parts) >= 3 and not docente:
            for part in parts[1:]:
                if SemanticParser._is_person_name(part):
                    docente = part
                    break
        
        if len(parts) >= 3 and not aula:
            for part in reversed(parts[1:]):
                if not SemanticParser._is_person_name(part) and part != docente:
                    if 'lab' in part.lower() or 'sal' in part.lower() or 'aula' in part.lower():
                        aula = part
                        break
        
        return {
            "materia": materia if materia else texto_limpio,
            "grupo": grupo,
            "docente": docente,
            "aula": aula,
            "texto_limpio": texto_limpio
        }
    
    @staticmethod
    def _is_person_name(text: str) -> bool:
        """Heurística simple para detectar si un texto es un nombre de persona"""
        if not text:
            return False
        
        words = text.split()
        if len(words) < 2:
            return False
        
        has_multiple_caps = sum(1 for w in words if w and w[0].isupper()) >= 2
        
        no_location_keywords = not any(kw in text.lower() for kw in 
            ['lab', 'laboratorio', 'sala', 'salón', 'aula', 'edificio', 'piso'])
        
        return has_multiple_caps and no_location_keywords and len(text) > 5
