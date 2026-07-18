from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from models import UploadResponse
from state import programas_dict, processors, limiter
from storage import storage
from routers.schedules import register_excel_file
from utils.pdf_converter import pdf_to_xlsx, is_pdf_file
from utils.import_json_helper import validate_import_json_structure, build_schedule_from_import_json
import tempfile
import shutil
import os
import logging
from datetime import datetime, timezone

router = APIRouter(tags=["Upload"])

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB — soporta PDFs grandes de oferta académica

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

    errors = validate_import_json_structure(data)

    if errors:
        raise HTTPException(status_code=422, detail={"message": "El JSON tiene errores de estructura", "errors": errors})

    schedule_dict, import_meta = build_schedule_from_import_json(
        data,
        programas_dict,
        default_filename="importado.json",
    )

    await storage.create(schedule_dict)

    return {
        "schedule_id": import_meta["schedule_id"],
        "message": "JSON importado exitosamente",
        "semestres": import_meta["semestres"],
        "programa": import_meta["programa"],
    }
