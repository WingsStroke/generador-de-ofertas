def _sheet_name_to_semestre(sheet_name: str) -> int:
    """Extrae el número de semestre del nombre de la hoja.
    'Table 1' -> 1, 'Table 2' -> 2, etc.
    Si no se puede parsear, devuelve 0.
    """
    import re
    match = re.search(r'\d+', str(sheet_name))
    return int(match.group()) if match else 0


def export_to_json_format(schedule: dict, diccionario: dict, global_diccionario: dict = None) -> dict:
    """Convierte el horario procesado al formato JSON de exportación especificado"""
    from collections import defaultdict

    def _normalize_name(name: str) -> str:
        """Normaliza un nombre para comparación: minúsculas, sin tildes, sin espacios extra."""
        import unicodedata
        if not name:
            return ""
        nfkd = unicodedata.normalize("NFKD", name.lower().strip())
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    def _derive_subject_id(name: str) -> str:
        import re
        norm = _normalize_name(name)
        if not norm:
            return "materia_sin_nombre"
        sid = re.sub(r'[^a-z0-9]+', '_', norm)
        sid = re.sub(r'_+', '_', sid).strip('_')
        return sid or "materia_sin_nombre"

    def process_celdas(celdas: list, semestre_num: int) -> dict:
        """Procesa las celdas de una hoja y devuelve un dict {materia_key: materia_data}.
        Agrupa materias por materia_id si está en el diccionario, o por nombre normalizado
        si no está, evitando duplicados cuando la misma materia aparece en múltiples celdas.
        """
        materias_map = {}
        global_dict = global_diccionario or {}

        for celda in celdas:
            dia = celda["dia"]
            hora_inicio = celda["hora_inicio"]
            hora_fin = celda["hora_fin"]

            for bloque in celda["bloques"]:
                raw_materia_id = bloque.get("materia_id")
                materia_nombre = bloque.get("materia") or ""
                grupo = bloque.get("grupo")
                if not grupo:
                    grupo = None
                docente = bloque.get("docente")
                aula = bloque.get("aula")

                creditos = None
                codigo = None

                if raw_materia_id:
                    materia_key = raw_materia_id
                else:
                    materia_key = _derive_subject_id(materia_nombre) if materia_nombre else f"materia_{bloque['id'][:8]}"

                if materia_key in diccionario:
                    creditos = diccionario[materia_key].get("creditos")
                    codigo = diccionario[materia_key].get("codigo")
                    if diccionario[materia_key].get("nombre_oficial"):
                        materia_nombre = diccionario[materia_key]["nombre_oficial"]
                elif materia_key in global_dict:
                    creditos = global_dict[materia_key].get("creditos")
                    codigo = global_dict[materia_key].get("codigo")
                    if global_dict[materia_key].get("nombre_oficial"):
                        materia_nombre = global_dict[materia_key]["nombre_oficial"]
                else:
                    creditos = bloque.get("creditos")
                    codigo = bloque.get("codigo")

                grupo_id = f"{materia_key}_{grupo.lower().replace(' ', '_')}" if grupo else f"{materia_key}_na"
                jornada = "nocturna" if int(hora_inicio.split(":")[0]) >= 18 else "diurna"

                horario_entry = {
                    "dia": dia,
                    "inicio": hora_inicio,
                    "fin": hora_fin,
                    "jornada": jornada,
                }

                if materia_key not in materias_map:
                    materias_map[materia_key] = {
                        "id": materia_key,
                        "nombre": materia_nombre,
                        "codigo": codigo,
                        "creditos": creditos,
                        "semestre": semestre_num,
                        "grupos": {},
                    }

                if grupo_id not in materias_map[materia_key]["grupos"]:
                    materias_map[materia_key]["grupos"][grupo_id] = {
                        "id": grupo_id,
                        "grupo": grupo,
                        "profesor": docente,
                        "ubicacion": aula,
                        "cupos": None,
                        "horarios": [],
                    }

                materias_map[materia_key]["grupos"][grupo_id]["horarios"].append(horario_entry)

        return materias_map

    hojas_data = schedule.get("hojas_data", {})

    if hojas_data and len(hojas_data) > 0:
        # Construir semestres_map global: semestre_num -> {materia_id: materia_data}
        semestres_map = defaultdict(dict)

        for hoja_nombre, hoja_info in hojas_data.items():
            semestre_num = _sheet_name_to_semestre(hoja_nombre)
            materias = process_celdas(hoja_info.get("celdas", []), semestre_num)
            for materia_id, materia_data in materias.items():
                if materia_id not in semestres_map[semestre_num]:
                    semestres_map[semestre_num][materia_id] = materia_data
                else:
                    # Fusionar grupos si la misma materia aparece en dos hojas del mismo semestre
                    for gid, gdata in materia_data["grupos"].items():
                        if gid not in semestres_map[semestre_num][materia_id]["grupos"]:
                            semestres_map[semestre_num][materia_id]["grupos"][gid] = gdata
                        else:
                            semestres_map[semestre_num][materia_id]["grupos"][gid]["horarios"].extend(
                                gdata["horarios"]
                            )
    else:
        semestre_num = 0
        semestres_map = defaultdict(dict)
        materias = process_celdas(schedule.get("celdas", []), semestre_num)
        semestres_map[semestre_num] = materias

    # Convertir semestres_map al array final
    semestres_list = []
    for num in sorted(semestres_map.keys()):
        asignaturas_list = []
        for materia_data in semestres_map[num].values():
            asignaturas_list.append({
                "id": materia_data["id"],
                "nombre": materia_data["nombre"],
                "codigo": materia_data.get("codigo"),
                "creditos": materia_data["creditos"],
                "semestre": materia_data["semestre"],
                "grupos": list(materia_data["grupos"].values()),
            })
        semestres_list.append({
            "numero": num,
            "asignaturas": asignaturas_list,
        })

    total_asignaturas = sum(len(s["asignaturas"]) for s in semestres_list)
    total_grupos = sum(
        sum(len(a["grupos"]) for a in s["asignaturas"]) for s in semestres_list
    )

    # Preparar datos de preview por hoja para poder reconstruir la vista sin XLSX
    preview_data_by_sheet = {}
    hojas_data = schedule.get("hojas_data", {})
    for hoja_nombre, hoja_info in hojas_data.items():
        preview_data_by_sheet[hoja_nombre] = {
            "excel_preview": hoja_info.get("excel_preview", []),
            "estructura_dias": hoja_info.get("estructura_dias", []),
            "estructura_horas": hoja_info.get("estructura_horas", []),
        }

    # ---------------------------------------------------------
    # Detección de Conflictos (Docentes y Aulas)
    # ---------------------------------------------------------
    conflictos = []
    docente_horarios = defaultdict(lambda: defaultdict(list))
    aula_horarios = defaultdict(lambda: defaultdict(list))

    def time_to_minutes(t: str) -> int:
        try:
            h, m = map(int, t.split(':'))
            return h * 60 + m
        except:
            return 0

    def overlap(start1, end1, start2, end2):
        return max(0, min(end1, end2) - max(start1, start2)) > 0

    for sem in semestres_list:
        for asig in sem["asignaturas"]:
            materia_nombre = asig["nombre"]
            for grp in asig["grupos"]:
                docente = grp.get("profesor")
                aula = grp.get("ubicacion")
                grupo_nom = grp.get("grupo", "N/A")
                
                for hor in grp.get("horarios", []):
                    dia = hor["dia"]
                    inicio_min = time_to_minutes(hor["inicio"])
                    fin_min = time_to_minutes(hor["fin"])
                    
                    event_info = {
                        "materia": materia_nombre,
                        "grupo": grupo_nom,
                        "inicio": hor["inicio"],
                        "fin": hor["fin"]
                    }
                    
                    # Chequear conflictos de docente
                    if docente and str(docente).strip().upper() not in ["", "N/A", "NULL", "POR DEFINIR", "POR ASIGNAR", "NO ASIGNADO"]:
                        doc_key = str(docente).strip().upper()
                        for exist in docente_horarios[doc_key][dia]:
                            if overlap(inicio_min, fin_min, exist["inicio_min"], exist["fin_min"]):
                                if materia_nombre == exist["materia"] and grupo_nom == exist["grupo"]:
                                    continue # Misma clase
                                conflictos.append({
                                    "tipo": "docente",
                                    "entidad": docente,
                                    "dia": dia,
                                    "hora": f"{hor['inicio']} - {hor['fin']}",
                                    "involucra": f"{materia_nombre} ({grupo_nom}) vs {exist['materia']} ({exist['grupo']})"
                                })
                        docente_horarios[doc_key][dia].append({**event_info, "inicio_min": inicio_min, "fin_min": fin_min})
                        
                    # Chequear conflictos de aula
                    if aula and str(aula).strip().upper() not in ["", "N/A", "NULL", "VIRTUAL", "POR DEFINIR", "POR ASIGNAR", "NO ASIGNADO"]:
                        aula_key = str(aula).strip().upper()
                        for exist in aula_horarios[aula_key][dia]:
                            if overlap(inicio_min, fin_min, exist["inicio_min"], exist["fin_min"]):
                                if materia_nombre == exist["materia"] and grupo_nom == exist["grupo"]:
                                    continue # Misma clase
                                conflictos.append({
                                    "tipo": "aula",
                                    "entidad": aula,
                                    "dia": dia,
                                    "hora": f"{hor['inicio']} - {hor['fin']}",
                                    "involucra": f"{materia_nombre} ({grupo_nom}) vs {exist['materia']} ({exist['grupo']})"
                                })
                        aula_horarios[aula_key][dia].append({**event_info, "inicio_min": inicio_min, "fin_min": fin_min})

    return {
        "metadata": {
            "programa": schedule.get("programa_nombre") or schedule.get("programa") or "Programa Académico",
            "archivo": schedule["nombre_archivo"],
            "fechaProcesamiento": schedule["fecha_procesamiento"],
            "totalAsignaturas": total_asignaturas,
            "totalGrupos": total_grupos,
            "totalSemestres": len(semestres_list),
            "version": "2.0.0",
            "conflictos": conflictos,
            "totalConflictos": len(conflictos),
        },
        "semestres": semestres_list,
        "_raw_preview_data": preview_data_by_sheet,  # Datos para reconstruir vista sin XLSX
    }
