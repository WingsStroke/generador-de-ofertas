def _sheet_name_to_semestre(sheet_name: str) -> int:
    """Extrae el número de semestre del nombre de la hoja.
    'Table 1' -> 1, 'Table 2' -> 2, etc.
    Si no se puede parsear, devuelve 0.
    """
    import re
    match = re.search(r'\d+', str(sheet_name))
    return int(match.group()) if match else 0


def export_to_json_format(schedule: dict, diccionario: dict) -> dict:
    """Convierte el horario procesado al formato JSON de exportación especificado"""
    from collections import defaultdict

    def _normalize_name(name: str) -> str:
        """Normaliza un nombre para comparación: minúsculas, sin tildes, sin espacios extra."""
        import unicodedata
        if not name:
            return ""
        nfkd = unicodedata.normalize("NFKD", name.lower().strip())
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    def process_celdas(celdas: list, semestre_num: int) -> dict:
        """Procesa las celdas de una hoja y devuelve un dict {materia_key: materia_data}.
        Agrupa materias por materia_id si está en el diccionario, o por nombre normalizado
        si no está, evitando duplicados cuando la misma materia aparece en múltiples celdas.
        """
        materias_map = {}
        # Mapa auxiliar: nombre_normalizado -> materia_key (para materias sin ID de diccionario)
        nombre_to_key = {}

        for celda in celdas:
            dia = celda["dia"]
            hora_inicio = celda["hora_inicio"]
            hora_fin = celda["hora_fin"]

            for bloque in celda["bloques"]:
                raw_materia_id = bloque.get("materia_id")
                materia_nombre = bloque.get("materia") or ""
                grupo = bloque.get("grupo") or "N/A"
                docente = bloque.get("docente")
                aula = bloque.get("aula")

                creditos = None

                # Si el bloque tiene un materia_id válido del diccionario, usarlo directamente
                if raw_materia_id and raw_materia_id in diccionario:
                    materia_key = raw_materia_id
                    creditos = diccionario[raw_materia_id].get("creditos")
                else:
                    # Sin ID válido: agrupar por nombre normalizado para evitar duplicados
                    nombre_norm = _normalize_name(materia_nombre)
                    if nombre_norm in nombre_to_key:
                        materia_key = nombre_to_key[nombre_norm]
                    else:
                        # Generar un ID estable basado en el nombre normalizado
                        materia_key = "electiva_" + nombre_norm.replace(" ", "_")[:30] if nombre_norm else "electiva_" + bloque["id"][:8]
                        nombre_to_key[nombre_norm] = materia_key

                grupo_id = f"{materia_key}_{grupo.lower().replace(' ', '_')}" if grupo and grupo != "N/A" else f"{materia_key}_na"
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

    return {
        "metadata": {
            "programa": schedule.get("programa_nombre") or schedule.get("programa") or "Programa Académico",
            "archivo": schedule["nombre_archivo"],
            "fechaProcesamiento": schedule["fecha_procesamiento"],
            "totalAsignaturas": total_asignaturas,
            "totalGrupos": total_grupos,
            "totalSemestres": len(semestres_list),
            "version": "2.0.0",
        },
        "semestres": semestres_list,
        "_raw_preview_data": preview_data_by_sheet,  # Datos para reconstruir vista sin XLSX
    }
