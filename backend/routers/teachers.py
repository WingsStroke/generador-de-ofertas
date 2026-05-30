from fastapi import APIRouter, Request, HTTPException
from storage.teachers_storage import teachers_storage
from storage import storage
from utils.semantic_parser import SemanticParser
from utils.schedule_helpers import _iter_celdas_collections

router = APIRouter(prefix="/teachers", tags=["Teachers"])

@router.get("")
async def get_teachers():
    """Obtiene la lista de todos los docentes en el diccionario"""
    return {"teachers": teachers_storage.get_all()}

@router.post("")
async def add_teacher(request: Request):
    """Añade uno o varios docentes al diccionario.
    Soporta comprobación de duplicados fuzzy.
    Si hay similares y force=False, retorna requires_confirmation=True sin añadir.
    Si force=True, añade aunque haya similares.
    """
    data = await request.json()
    if "name" in data:
        force = bool(data.get("force", False))
        result = teachers_storage.add(data["name"], force=force)
        if result.get("requires_confirmation"):
            return {
                "message": "Se encontraron docentes similares en el diccionario.",
                "added": False,
                "requires_confirmation": True,
                "similar": result["similar"],
                "normalized": result["normalized"]
            }
        return {
            "message": "Docente añadido" if result["added"] else "Docente ya existe",
            "added": result["added"],
            "normalized": result.get("normalized", "")
        }
    elif "names" in data and isinstance(data["names"], list):
        added = teachers_storage.add_multiple(data["names"])
        return {"message": f"{added} docentes añadidos", "added": added}
    raise HTTPException(status_code=400, detail="Se requiere 'name' o lista 'names'")

@router.delete("/{name}")
async def remove_teacher(name: str):
    """Elimina un docente del diccionario. Operación idempotente: no lanza 404 si no existe."""
    removed = teachers_storage.remove(name)
    return {"message": "Docente eliminado" if removed else "Docente no encontrado (ya eliminado)", "removed": removed}

@router.patch("/{name}")
async def replace_teacher(name: str, request: Request):
    """Reemplaza/fusiona un docente con otro nombre (para resolver duplicados)."""
    data = await request.json()
    new_name = data.get("new_name", "")
    if not new_name:
        raise HTTPException(status_code=400, detail="Se requiere 'new_name'")
    replaced = teachers_storage.replace(name, new_name)
    if not replaced:
        raise HTTPException(status_code=404, detail="Docente original no encontrado")
    return {"message": "Docente actualizado", "old": name, "new": new_name}

@router.post("/extract-from-schedule/{schedule_id}")
async def extract_teachers_from_schedule(schedule_id: str):
    """Extrae y guarda todos los docentes válidos de un horario"""
    schedule = await storage.get(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    
    docentes_encontrados = set()
    for celdas in _iter_celdas_collections(schedule):
        for cell in celdas:
            for block in cell.get("bloques", []):
                docente = block.get("docente")
                if docente and len(docente.strip()) > 3 and docente.upper() not in ["N/A", "NULL", "POR DEFINIR", "POR ASIGNAR"]:
                    # Usar la heurística de SemanticParser para asegurar que parece un nombre real
                    if SemanticParser._is_person_name(docente.strip()):
                        docentes_encontrados.add(docente.strip())
    
    added = teachers_storage.add_multiple(list(docentes_encontrados))
    return {
        "message": f"Se escanearon {len(docentes_encontrados)} docentes únicos. {added} nuevos añadidos al diccionario.",
        "scanned": len(docentes_encontrados),
        "added": added
    }
