"""Lector de "catálogo" de asignaturas: tabla auxiliar a la derecha del horario
con columnas NOMBRE ASIGNATURA | HORAS | CODIGO | GRUPO | NOMBRE DOCENTE.
Detección agnóstica al programa: se busca en cada hoja independientemente.
"""
import re
import unicodedata
from typing import Dict, List, Optional, Tuple
from rapidfuzz import fuzz


CATALOG_HEADERS = {
    "materia": ["NOMBRE ASIGNATURA", "ASIGNATURA", "NOMBRE DE LA ASIGNATURA"],
    "horas": ["HORAS"],
    "codigo": ["CODIGO DE ASIGNATURA", "CÓDIGO DE ASIGNATURA", "CODIGO", "CÓDIGO"],
    "grupo": ["GRUPO"],
    "docente": ["NOMBRE DOCENTE", "DOCENTE", "NOMBRE DEL DOCENTE", "PROFESOR"],
}


def _normalize(s: str) -> str:
    if not s:
        return ""
    s = str(s).strip().upper()
    # Quitar acentos
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    # Colapsar espacios
    s = re.sub(r"\s+", " ", s)
    return s


def _norm_grupo(g: str) -> str:
    if not g:
        return ""
    return str(g).strip().upper().replace(" ", "")


def detect_catalog(worksheet, days_end_col: int, max_scan_rows: int = 30) -> Optional[Dict]:
    """Detecta la tabla catálogo a la derecha de la última columna de días.
    Devuelve dict con `header_row`, `columns: {key: col_idx}` o None si no hay.
    """
    max_row = min(worksheet.max_row, max_scan_rows)
    max_col = worksheet.max_column

    for row_idx in range(1, max_row + 1):
        found = {}
        for col_idx in range(days_end_col + 1, max_col + 1):
            value = worksheet.cell(row=row_idx, column=col_idx).value
            if not isinstance(value, str):
                continue
            norm = _normalize(value)
            for key, headers in CATALOG_HEADERS.items():
                if key in found:
                    continue
                for h in headers:
                    if _normalize(h) in norm:
                        found[key] = col_idx
                        break
        # Aceptar si tiene materia + grupo + docente (mínimo viable)
        if "materia" in found and "grupo" in found and "docente" in found:
            return {"header_row": row_idx, "columns": found}
    return None


def read_catalog_entries(worksheet, catalog: Dict) -> List[Dict]:
    """Lee las filas del catálogo. Devuelve lista de entries con campos normalizados."""
    cols = catalog["columns"]
    start_row = catalog["header_row"] + 1
    max_row = worksheet.max_row

    entries = []
    for r in range(start_row, max_row + 1):
        materia = worksheet.cell(row=r, column=cols["materia"]).value
        if not materia or not str(materia).strip():
            continue

        materia_str = str(materia).strip()
        if len(materia_str) < 3:
            continue
        # Filtrar filas tipo "TOTAL" / "OBSERVACIONES"
        if _normalize(materia_str) in ("TOTAL", "OBSERVACIONES", "NOTA"):
            continue

        entry = {
            "materia": materia_str,
            "materia_norm": _normalize(materia_str),
            "grupo": "",
            "grupo_norm": "",
            "docente": None,
            "codigo": None,
            "horas": None,
            "row": r,
        }

        if "grupo" in cols:
            v = worksheet.cell(row=r, column=cols["grupo"]).value
            if v:
                entry["grupo"] = str(v).strip()
                entry["grupo_norm"] = _norm_grupo(v)
        if "docente" in cols:
            v = worksheet.cell(row=r, column=cols["docente"]).value
            if v:
                entry["docente"] = str(v).strip()
        if "codigo" in cols:
            v = worksheet.cell(row=r, column=cols["codigo"]).value
            if v:
                entry["codigo"] = str(v).strip()
        if "horas" in cols:
            v = worksheet.cell(row=r, column=cols["horas"]).value
            if v is not None:
                entry["horas"] = v

        entries.append(entry)

    return entries


def find_match(entries: List[Dict], materia: Optional[str], grupo: Optional[str],
               threshold: int = 85) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Busca la mejor entry para (materia, grupo).

    Devuelve (best_match, single_group_match):
      - best_match: entry con mayor score si materia ≥ threshold y grupo coincide.
      - single_group_match: si el bloque no tiene grupo y la materia tiene un único
        grupo en el catálogo, esa entry (para asignación automática).
    """
    if not materia:
        return None, None

    materia_norm = _normalize(materia)
    grupo_norm = _norm_grupo(grupo) if grupo else ""

    # Materias candidatas (score ≥ threshold)
    candidates = []
    for e in entries:
        score = fuzz.token_set_ratio(materia_norm, e["materia_norm"])
        if score >= threshold:
            candidates.append((score, e))

    if not candidates:
        return None, None

    # Ordenar por score descendente
    candidates.sort(key=lambda x: x[0], reverse=True)

    # Si tenemos grupo, exigir match exacto de grupo
    if grupo_norm:
        for score, e in candidates:
            if e["grupo_norm"] == grupo_norm:
                return e, None
        return None, None

    # Sin grupo: si todos los candidatos top tienen el MISMO grupo, asignar; sino None
    top_score = candidates[0][0]
    top_candidates = [e for s, e in candidates if s >= top_score - 5]
    unique_groups = {e["grupo_norm"] for e in top_candidates if e["grupo_norm"]}
    if len(unique_groups) == 1:
        return None, top_candidates[0]
    return None, None
