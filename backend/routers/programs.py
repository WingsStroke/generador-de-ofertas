from fastapi import APIRouter, HTTPException, Request
from typing import List
from models import ProgramaAcademico, Subject
from state import programas_dict, limiter

router = APIRouter(tags=["Programs"])

@router.get("/programs", response_model=List[ProgramaAcademico])
async def get_programs():
    """Obtiene la lista de programas académicos disponibles"""
    programs = []
    for prog_id, prog_data in programas_dict.items():
        programs.append(ProgramaAcademico(
            id=prog_id,
            nombre=prog_data["nombre"],
            total_materias=prog_data["total_materias"]
        ))
    return programs

@router.get("/subjects", response_model=List[Subject])
async def get_subjects(program_id: str = "ingenieria_de_sistemas"):
    """Obtiene el diccionario de materias de un programa específico"""
    if program_id not in programas_dict:
        raise HTTPException(status_code=400, detail=f"Programa '{program_id}' no encontrado")
    
    subject_dict = programas_dict[program_id]["diccionario"]
    subjects = []
    for subject_id, data in subject_dict.items():
        subjects.append(Subject(
            id=subject_id,
            nombre_oficial=data["nombre_oficial"],
            codigo=data.get("codigo"),
            creditos=data.get("creditos")
        ))
    return subjects

@router.get("/subjects/search/{query}")
@limiter.limit("30/minute")
async def search_subjects(request: Request, query: str, program_id: str = "ingenieria_de_sistemas", limit: int = 10):
    """
    Busca materias por texto con fuzzy matching en un programa específico.
    
    Rate limit: 30 búsquedas por minuto por IP.
    """
    if len(query) > 100:
        raise HTTPException(status_code=400, detail="Query demasiado largo (máx 100 caracteres)")
    if program_id not in programas_dict:
        raise HTTPException(status_code=400, detail=f"Programa '{program_id}' no encontrado")
    
    from utils.subject_matcher import SubjectMatcher
    subject_dict = programas_dict[program_id]["diccionario"]
    matcher = SubjectMatcher(subject_dict)
    suggestions = matcher.get_suggestions(query, limit=limit)
    
    results = []
    for subject_id, name, confidence in suggestions:
        results.append({
            "id": subject_id,
            "nombre": name,
            "confidence": confidence,
            "codigo": subject_dict[subject_id].get("codigo"),
            "creditos": subject_dict[subject_id].get("creditos")
        })
    
    return results
