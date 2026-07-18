from fastapi import APIRouter, HTTPException, Request, Depends
from typing import List
from models import ProgramaAcademico, Subject, GlobalSubjectUpsert
from state import programas_dict, limiter
from routers.auth import get_current_admin
from storage.subjects_storage import subjects_storage
from utils.subject_utils import derive_subject_id
from utils.program_loader import get_program_subjects, refresh_all_program_processors

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

    subject_dict = get_program_subjects(program_id)
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
    subject_dict = get_program_subjects(program_id)
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


@router.get("/subjects/global", response_model=List[Subject])
async def get_global_subjects():
    """Lista el diccionario global de asignaturas."""
    subjects = []
    for item in subjects_storage.get_all():
        subjects.append(Subject(
            id=item["id"],
            nombre_oficial=item["nombre_oficial"],
            codigo=item.get("codigo"),
            creditos=item.get("creditos"),
        ))
    return subjects


@router.post("/subjects/global", response_model=Subject)
async def upsert_global_subject(payload: GlobalSubjectUpsert, admin: dict = Depends(get_current_admin)):
    """Crea o actualiza una asignatura en el diccionario global (solo admin)."""
    subject_id = payload.id or derive_subject_id(payload.nombre_oficial)

    # No permitir sobrescritura de materias del diccionario base.
    for program_data in programas_dict.values():
        if subject_id in program_data.get("diccionario", {}):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No se puede sobrescribir la materia base '{subject_id}'. "
                    "El diccionario base del programa tiene prioridad."
                )
            )

    saved = subjects_storage.upsert(
        subject_id=subject_id,
        nombre_oficial=payload.nombre_oficial,
        codigo=payload.codigo,
        creditos=payload.creditos,
    )
    refresh_all_program_processors()
    return Subject(
        id=saved["id"],
        nombre_oficial=saved["nombre_oficial"],
        codigo=saved.get("codigo"),
        creditos=saved.get("creditos"),
    )


@router.delete("/subjects/global/{subject_id}")
async def delete_global_subject(subject_id: str, admin: dict = Depends(get_current_admin)):
    deleted = subjects_storage.delete(subject_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Asignatura global no encontrada")
    refresh_all_program_processors()
    return {"message": "Asignatura global eliminada", "id": subject_id}
