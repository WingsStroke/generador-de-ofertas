import uuid
from datetime import datetime, timezone
from typing import Dict, List, Tuple


def validate_import_json_structure(data: Dict) -> List[str]:
    errors: List[str] = []

    if "metadata" not in data:
        errors.append("Falta la sección 'metadata'")
    if "semestres" not in data:
        errors.append("Falta la sección 'semestres'")
        return errors

    if not isinstance(data["semestres"], list):
        errors.append("'semestres' debe ser una lista")
        return errors

    for i, sem in enumerate(data["semestres"]):
        if not isinstance(sem, dict):
            errors.append(f"semestres[{i}]: debe ser un objeto")
            continue
        if "numero" not in sem:
            errors.append(f"semestres[{i}]: falta 'numero'")
        if "asignaturas" not in sem or not isinstance(sem.get("asignaturas"), list):
            errors.append(f"semestres[{i}]: falta 'asignaturas' (lista)")
            continue

        for j, asig in enumerate(sem.get("asignaturas", [])):
            if not isinstance(asig, dict):
                errors.append(f"semestres[{i}].asignaturas[{j}]: debe ser un objeto")
                continue
            for campo in ("id", "nombre", "grupos"):
                if campo not in asig:
                    errors.append(f"semestres[{i}].asignaturas[{j}]: falta '{campo}'")

            for k, grp in enumerate(asig.get("grupos", [])):
                if not isinstance(grp, dict):
                    errors.append(f"semestres[{i}].asignaturas[{j}].grupos[{k}]: debe ser un objeto")
                    continue
                for campo in ("id", "grupo", "horarios"):
                    if campo not in grp:
                        errors.append(f"semestres[{i}].asignaturas[{j}].grupos[{k}]: falta '{campo}'")

                for h, hor in enumerate(grp.get("horarios", [])):
                    for campo in ("dia", "inicio", "fin"):
                        if campo not in hor:
                            errors.append(
                                f"semestres[{i}].asignaturas[{j}].grupos[{k}].horarios[{h}]: falta '{campo}'"
                            )

    return errors


def build_schedule_from_import_json(
    data: Dict,
    programas_dict: Dict,
    default_filename: str = "importado.json",
) -> Tuple[Dict, Dict]:
    meta = data.get("metadata", {})
    programa_nombre = meta.get("programa", "Programa importado")
    nombre_archivo = meta.get("archivo", default_filename)
    fecha = meta.get("fechaProcesamiento", datetime.now(timezone.utc).isoformat())

    programa_id = "ingenieria_de_sistemas"
    for pid, pdata in programas_dict.items():
        nombre = str(pdata.get("nombre", "")).lower()
        programa_lower = str(programa_nombre).lower()
        if nombre in programa_lower or programa_lower in nombre:
            programa_id = pid
            break

    preview_data = data.get("_raw_preview_data", {})
    hojas_data = {}

    for sem in data.get("semestres", []):
        num = sem.get("numero", 0)
        sheet_name = f"Table {num}" if num > 0 else "Table 1"
        celdas = []

        for asig in sem.get("asignaturas", []):
            materia_id = asig.get("id")
            materia_nombre = asig.get("nombre")
            creditos = asig.get("creditos")

            for grp in asig.get("grupos", []):
                grupo_label = grp.get("grupo")
                if not grupo_label or str(grupo_label).strip() in ("N/A", ""):
                    grupo_label = None

                docente = grp.get("profesor")
                aula = grp.get("ubicacion")

                for hor in grp.get("horarios", []):
                    dia = hor.get("dia")
                    hora_inicio = hor.get("inicio")
                    hora_fin = hor.get("fin")

                    existing = next(
                        (
                            c for c in celdas
                            if c.get("dia") == dia
                            and c.get("hora_inicio") == hora_inicio
                            and c.get("hora_fin") == hora_fin
                        ),
                        None,
                    )

                    bloque = {
                        "id": str(uuid.uuid4()),
                        "materia": materia_nombre,
                        "materia_id": materia_id,
                        "grupo": grupo_label,
                        "docente": docente,
                        "aula": aula,
                        "creditos": creditos,
                        "horarios": [{
                            "dia": dia,
                            "hora_inicio": hora_inicio,
                            "hora_fin": hora_fin,
                            "bloques_cantidad": 1,
                        }],
                        "nivel_confianza": 1.0,
                        "estado": "confirmed",
                    }

                    if existing:
                        existing.setdefault("bloques", []).append(bloque)
                    else:
                        celdas.append({
                            "dia": dia,
                            "hora_inicio": hora_inicio,
                            "hora_fin": hora_fin,
                            "celda_ref": f"{dia}_{hora_inicio}",
                            "bloques": [bloque],
                        })

        sheet_preview = preview_data.get(sheet_name, {})
        hojas_data[sheet_name] = {
            "nombre": sheet_name,
            "celdas": celdas,
            "estructura_dias": sheet_preview.get("estructura_dias", []),
            "estructura_horas": sheet_preview.get("estructura_horas", []),
            "excel_preview": sheet_preview.get("excel_preview", []),
            "html_preview": sheet_preview.get("html_preview"),
            "nivel_confianza": 1.0,
        }

    first_sheet = list(hojas_data.keys())[0] if hojas_data else "Table 1"
    first_celdas = hojas_data[first_sheet]["celdas"] if hojas_data else []
    first_sheet_data = hojas_data.get(first_sheet, {}) if hojas_data else {}

    schedule_id = str(uuid.uuid4())
    schedule_dict = {
        "id": schedule_id,
        "nombre_archivo": nombre_archivo,
        "fecha_procesamiento": fecha,
        "programa_id": programa_id,
        "programa_nombre": programa_nombre,
        "programa": programa_nombre,
        "hoja_actual": first_sheet,
        "hojas": list(hojas_data.keys()),
        "hojas_data": hojas_data,
        "celdas": first_celdas,
        "estructura_dias": first_sheet_data.get("estructura_dias", []),
        "estructura_horas": first_sheet_data.get("estructura_horas", []),
        "excel_preview": first_sheet_data.get("excel_preview", []),
        "html_preview": first_sheet_data.get("html_preview"),
        "nivel_confianza_global": 1.0,
        "_v": 0,
    }

    return schedule_dict, {
        "schedule_id": schedule_id,
        "semestres": len(data.get("semestres", [])),
        "programa": programa_nombre,
    }