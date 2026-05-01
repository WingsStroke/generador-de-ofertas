def export_to_json_format(schedule: dict, diccionario: dict) -> dict:
    """Convierte el horario procesado al formato JSON de exportación especificado"""
    from collections import defaultdict
    
    def process_sheet_data(celdas: list, sheet_name: str = None):
        """Procesa una hoja individual"""
        semestres_map = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        
        for celda in celdas:
            dia = celda["dia"]
            hora_inicio = celda["hora_inicio"]
            hora_fin = celda["hora_fin"]
            
            for bloque in celda["bloques"]:
                materia_id = bloque.get("materia_id") or "electiva_" + bloque["id"][:8]
                materia_nombre = bloque["materia"]
                grupo = bloque["grupo"] or "N/A"
                docente = bloque.get("docente")
                aula = bloque.get("aula")
                
                semestre_num = 0
                creditos = None
                if materia_id in diccionario:
                    creditos = diccionario[materia_id].get("creditos")
                
                grupo_id = f"{materia_id}_{grupo.lower()}" if grupo else f"{materia_id}_na"
                
                jornada = "nocturna" if int(hora_inicio.split(":")[0]) >= 18 else "diurna"
                
                horario_entry = {
                    "dia": dia,
                    "inicio": hora_inicio,
                    "fin": hora_fin,
                    "jornada": jornada
                }
                
                if materia_id not in semestres_map[semestre_num]:
                    semestres_map[semestre_num][materia_id] = {
                        "id": materia_id,
                        "nombre": materia_nombre,
                        "creditos": creditos,
                        "semestre": semestre_num,
                        "grupos": {}
                    }
                
                if grupo_id not in semestres_map[semestre_num][materia_id]["grupos"]:
                    semestres_map[semestre_num][materia_id]["grupos"][grupo_id] = {
                        "id": grupo_id,
                        "grupo": grupo,
                        "profesor": docente,
                        "ubicacion": aula,
                        "cupos": None,
                        "horarios": []
                    }
                
                semestres_map[semestre_num][materia_id]["grupos"][grupo_id]["horarios"].append(horario_entry)
        
        semestres_list = []
        for semestre_num in sorted(semestres_map.keys()):
            asignaturas_list = []
            for materia_id, materia_data in semestres_map[semestre_num].items():
                grupos_list = list(materia_data["grupos"].values())
                asignaturas_list.append({
                    "id": materia_data["id"],
                    "nombre": materia_data["nombre"],
                    "creditos": materia_data["creditos"],
                    "semestre": materia_data["semestre"],
                    "grupos": grupos_list
                })
            
            semestres_list.append({
                "numero": semestre_num,
                "asignaturas": asignaturas_list
            })
        
        return semestres_list
    
    hojas_data = schedule.get("hojas_data", {})
    
    if hojas_data and len(hojas_data) > 0:
        hojas_export = []
        total_asignaturas = 0
        total_grupos = 0
        
        for hoja_nombre, hoja_info in hojas_data.items():
            semestres = process_sheet_data(hoja_info["celdas"], hoja_nombre)
            
            sheet_asignaturas = sum(len(s["asignaturas"]) for s in semestres)
            sheet_grupos = sum(
                sum(len(asig["grupos"]) for asig in s["asignaturas"]) 
                for s in semestres
            )
            
            total_asignaturas += sheet_asignaturas
            total_grupos += sheet_grupos
            
            hojas_export.append({
                "nombre": hoja_nombre,
                "confianza": hoja_info.get("nivel_confianza", 0.0),
                "totalAsignaturas": sheet_asignaturas,
                "totalGrupos": sheet_grupos,
                "semestres": semestres
            })
        
        return {
            "metadata": {
                "programa": schedule.get("programa_nombre") or schedule.get("programa") or "Programa Académico",
                "archivo": schedule["nombre_archivo"],
                "fechaProcesamiento": schedule["fecha_procesamiento"],
                "totalHojas": len(hojas_export),
                "totalAsignaturas": total_asignaturas,
                "totalGrupos": total_grupos,
                "version": "2.0.0"
            },
            "hojas": hojas_export
        }
    else:
        semestres = process_sheet_data(schedule["celdas"])
        
        total_asignaturas = sum(len(s["asignaturas"]) for s in semestres)
        total_grupos = sum(
            sum(len(asig["grupos"]) for asig in s["asignaturas"]) 
            for s in semestres
        )
        
        return {
            "metadata": {
                "programa": schedule.get("programa_nombre") or schedule.get("programa") or "Programa Académico",
                "archivo": schedule["nombre_archivo"],
                "fechaProcesamiento": schedule["fecha_procesamiento"],
                "totalAsignaturas": total_asignaturas,
                "totalGrupos": total_grupos,
                "totalSemestres": len(semestres),
                "version": "2.0.0"
            },
            "semestres": semestres
        }
