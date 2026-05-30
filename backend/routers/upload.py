from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from models import UploadResponse
from state import programas_dict, processors, limiter
from storage import storage
from routers.schedules import register_excel_file
from utils.pdf_converter import pdf_to_xlsx, is_pdf_file
import tempfile
import shutil
import os
import logging
import uuid
from datetime import datetime, timezone

router = APIRouter(tags=["Upload"])

MAX_FILE_SIZE = 10 * 1024 * 1024

EXCEL_SIGNATURES = {
    b'\x50\x4B\x03\x04': 'xlsx',  # ZIP (XLSX es un ZIP)
    b'\xD0\xCF\x11\xE0': 'xls',   # OLE Compound Document (XLS antiguo)
}

PDF_SIGNATURE = b'%PDF'

ALLOWED_MIME_TYPES = {
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # .xlsx
    'application/vnd.ms-excel',  # .xls
    'application/octet-stream',  # Algunos navegadores envían esto
    'application/pdf',           # PDF
}

async def validate_excel_file(file: UploadFile) -> tuple[bool, str]:
    """
    Valida que el archivo sea un Excel genuino.
    """
    content = await file.read(4096)
    if len(content) < 4:
        return False, "Archivo vacío o demasiado pequeño"
    
    is_valid_signature = False
    for signature, fmt in EXCEL_SIGNATURES.items():
        if content.startswith(signature):
            is_valid_signature = True
            break
    
    if not is_valid_signature:
        return False, "El archivo no tiene formato Excel válido (firma mágica inválida)"
    
    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        if file.content_type != 'application/octet-stream':
            return False, f"Tipo de archivo no permitido: {file.content_type}"
    
    await file.seek(0)
    tmp_path = None
    try:
        full_content = await file.read()
        
        if len(full_content) > MAX_FILE_SIZE:
            return False, f"Archivo demasiado grande (máx {MAX_FILE_SIZE // (1024*1024)}MB)"
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            tmp.write(full_content)
            tmp_path = tmp.name
        
        try:
            import openpyxl
            wb = openpyxl.load_workbook(tmp_path, data_only=True, read_only=True)
            sheet_names = wb.sheetnames
            wb.close()
            
            if not sheet_names:
                return False, "El archivo Excel no contiene hojas"
            
        except Exception as e:
            return False, f"El archivo no es un Excel válido: {str(e)}"
        
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
        
        await file.seek(0)
        return True, ""
        
    except Exception as e:
        return False, f"Error validando archivo: {str(e)}"

@router.post("/upload", response_model=UploadResponse)
@limiter.limit("5/minute")
async def upload_schedule(request: Request, file: UploadFile = File(...), program_id: str = "ingenieria_de_sistemas"):
    allowed_extensions = ('.xlsx', '.xls', '.pdf')
    if not file.filename.lower().endswith(allowed_extensions):
        raise HTTPException(
            status_code=400,
            detail="Solo se permiten archivos Excel (.xlsx, .xls) o PDF (.pdf)"
        )

    if program_id not in programas_dict:
        raise HTTPException(status_code=400, detail=f"Programa '{program_id}' no encontrado")

    # ── Leer los primeros bytes para detectar el tipo real del archivo ──
    header_bytes = await file.read(8)
    await file.seek(0)
    file_is_pdf = is_pdf_file(file.filename, header_bytes)

    if file_is_pdf:
        # ── Ruta PDF: guardar temporal → convertir a XLSX ──────────────────
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_pdf:
            shutil.copyfileobj(file.file, tmp_pdf)
            tmp_pdf_path = tmp_pdf.name

        tmp_path_for_cleanup = tmp_pdf_path
        converted_xlsx_path = None
        persistent_excel_path = None

        try:
            logging.info(f"Convirtiendo PDF a XLSX: {file.filename}")
            converted_xlsx_path = pdf_to_xlsx(tmp_pdf_path)
            tmp_path = converted_xlsx_path  # a partir de aquí se procesa igual

        except (ValueError, RuntimeError) as conv_err:
            logging.error(f"Error convirtiendo PDF '{file.filename}': {conv_err}")
            raise HTTPException(
                status_code=422,
                detail=f"No se pudo convertir el PDF: {conv_err}"
            )
        except ImportError as imp_err:
            logging.error(f"Dependencia faltante para conversión PDF: {imp_err}")
            raise HTTPException(
                status_code=500,
                detail=str(imp_err)
            )

    else:
        # ── Ruta Excel: validación + guardado temporal ──────────────────────
        is_valid, error_msg = await validate_excel_file(file)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Archivo inválido: {error_msg}")

        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
            shutil.copyfileobj(file.file, tmp_file)
            tmp_path = tmp_file.name

        tmp_path_for_cleanup = tmp_path
        converted_xlsx_path = None
        persistent_excel_path = None

    # ── Procesamiento común (PDF o Excel, ambos llegan como .xlsx) ─────────
    try:
        processor = processors[program_id]
        programa_nombre = programas_dict[program_id]["nombre"]
        schedule = processor.process_file(tmp_path, file.filename, program_id, programa_nombre)

        schedule_dict = schedule.model_dump()
        schedule_dict['fecha_procesamiento'] = schedule_dict['fecha_procesamiento'].isoformat()
        schedule_dict['_v'] = 0

        await storage.create(schedule_dict)

        # Guardar copia persistente del Excel para el visor HTML
        persistent_excel_path = tmp_path + f"_preview_{schedule.id}.xlsx"
        shutil.copy2(tmp_path, persistent_excel_path)
        register_excel_file(schedule.id, persistent_excel_path)

        return UploadResponse(
            schedule_id=schedule.id,
            message="Archivo procesado exitosamente",
            confianza_global=schedule.nivel_confianza_global
        )

    except HTTPException:
        raise

    except Exception as e:
        logging.error(f"Error procesando archivo: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error interno al procesar el archivo. Por favor intente nuevamente o contacte soporte."
        )

    finally:
        # Limpiar el archivo fuente temporal (PDF o XLSX original)
        if tmp_path_for_cleanup and os.path.exists(tmp_path_for_cleanup):
            try:
                os.unlink(tmp_path_for_cleanup)
            except OSError as e:
                logging.warning(f"No se pudo eliminar archivo temporal {tmp_path_for_cleanup}: {e}")
        # Limpiar el XLSX convertido (solo existe en ruta PDF)
        if converted_xlsx_path and converted_xlsx_path != tmp_path_for_cleanup and os.path.exists(converted_xlsx_path):
            try:
                os.unlink(converted_xlsx_path)
            except OSError as e:
                logging.warning(f"No se pudo eliminar XLSX convertido {converted_xlsx_path}: {e}")


@router.post("/import-json")
async def import_json_schedule(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="El archivo no es un JSON válido")

    errors = []
    if "metadata" not in data: errors.append("Falta la sección 'metadata'")
    if "semestres" not in data: errors.append("Falta la sección 'semestres'")
    else:
        if not isinstance(data["semestres"], list): errors.append("'semestres' debe ser una lista")
        else:
            for i, sem in enumerate(data["semestres"]):
                if not isinstance(sem, dict):
                    errors.append(f"semestres[{i}]: debe ser un objeto")
                    continue
                if "numero" not in sem: errors.append(f"semestres[{i}]: falta 'numero'")
                if "asignaturas" not in sem or not isinstance(sem.get("asignaturas"), list):
                    errors.append(f"semestres[{i}]: falta 'asignaturas' (lista)")
                    continue
                for j, asig in enumerate(sem.get("asignaturas", [])):
                    if not isinstance(asig, dict):
                        errors.append(f"semestres[{i}].asignaturas[{j}]: debe ser un objeto")
                        continue
                    for campo in ("id", "nombre", "grupos"):
                        if campo not in asig: errors.append(f"semestres[{i}].asignaturas[{j}]: falta '{campo}'")
                    for k, grp in enumerate(asig.get("grupos", [])):
                        if not isinstance(grp, dict):
                            errors.append(f"semestres[{i}].asignaturas[{j}].grupos[{k}]: debe ser un objeto")
                            continue
                        for campo in ("id", "grupo", "horarios"):
                            if campo not in grp: errors.append(f"semestres[{i}].asignaturas[{j}].grupos[{k}]: falta '{campo}'")
                        for h, hor in enumerate(grp.get("horarios", [])):
                            for campo in ("dia", "inicio", "fin"):
                                if campo not in hor:
                                    errors.append(f"semestres[{i}].asignaturas[{j}].grupos[{k}].horarios[{h}]: falta '{campo}'")

    if errors:
        raise HTTPException(status_code=422, detail={"message": "El JSON tiene errores de estructura", "errors": errors})

    meta = data.get("metadata", {})
    programa_nombre = meta.get("programa", "Programa importado")
    nombre_archivo = meta.get("archivo", "importado.json")
    fecha = meta.get("fechaProcesamiento", datetime.now(timezone.utc).isoformat())

    programa_id = "ingenieria_de_sistemas"
    for pid, pdata in programas_dict.items():
        if pdata["nombre"].lower() in programa_nombre.lower() or programa_nombre.lower() in pdata["nombre"].lower():
            programa_id = pid
            break

    preview_data = data.get("_raw_preview_data", {})
    hojas_data = {}

    for sem in data["semestres"]:
        num = sem.get("numero", 0)
        sheet_name = f"Table {num}" if num > 0 else "Table 1"
        celdas = []

        for asig in sem.get("asignaturas", []):
            materia_id = asig["id"]
            materia_nombre = asig["nombre"]
            creditos = asig.get("creditos")
            for grp in asig.get("grupos", []):
                grupo_label = grp.get("grupo")
                if not grupo_label or str(grupo_label).strip() == "N/A" or str(grupo_label).strip() == "":
                    grupo_label = None
                docente = grp.get("profesor")
                aula = grp.get("ubicacion")
                for hor in grp.get("horarios", []):
                    dia = hor["dia"]
                    hora_inicio = hor["inicio"]
                    hora_fin = hor["fin"]

                    existing = next(
                        (c for c in celdas if c["dia"] == dia and c["hora_inicio"] == hora_inicio and c["hora_fin"] == hora_fin),
                        None
                    )
                    bloque = {
                        "id": str(uuid.uuid4()),
                        "materia": materia_nombre,
                        "materia_id": materia_id,
                        "grupo": grupo_label,
                        "docente": docente,
                        "aula": aula,
                        "creditos": creditos,
                        "horarios": [{"dia": dia, "hora_inicio": hora_inicio, "hora_fin": hora_fin, "bloques_cantidad": 1}],
                        "nivel_confianza": 1.0,
                        "estado": "confirmed",
                    }
                    if existing:
                        existing["bloques"].append(bloque)
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
        "nivel_confianza_global": 1.0,
        "_v": 0,
    }

    await storage.create(schedule_dict)

    return {
        "schedule_id": schedule_id,
        "message": "JSON importado exitosamente",
        "semestres": len(data["semestres"]),
        "programa": programa_nombre,
    }
