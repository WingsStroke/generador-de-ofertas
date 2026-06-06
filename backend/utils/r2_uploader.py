"""
r2_uploader.py
==============
Módulo para publicar archivos JSON de oferta académica en Cloudflare R2.

Cloudflare R2 es compatible con la API de Amazon S3, por eso usamos boto3.
El cliente se configura apuntando al endpoint de R2 de la cuenta.

Variables de entorno requeridas (en backend/.env):
    R2_ACCOUNT_ID        — ID de cuenta de Cloudflare (ej. abc123...)
    R2_ACCESS_KEY_ID     — Access Key ID del token R2
    R2_SECRET_ACCESS_KEY — Secret Access Key del token R2
    R2_BUCKET_NAME       — Nombre del bucket (ej. ofertas-academicas)
    R2_PUBLIC_URL        — URL pública base del bucket (ej. https://pub-xxx.r2.dev)

Estructura del bucket generada:
    bucket/
    ├── index.json                     ← índice global de semestres (actualizado automáticamente)
    ├── 2026-1/
    │   ├── sistemas.xlsx.json
    │   └── alimentos.xlsx.json
    └── 2026-2/
        └── sistemas.xlsx.json
"""

import json
import logging
import os
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def is_r2_configured() -> bool:
    """Verifica si todas las variables de entorno de R2 están presentes."""
    required = [
        "R2_ACCOUNT_ID",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET_NAME",
        "R2_PUBLIC_URL",
    ]
    return all(os.getenv(k) for k in required)


def _get_r2_client():
    """Crea y devuelve un cliente boto3 apuntando al endpoint de R2."""
    try:
        import boto3
        from botocore.client import Config
    except ImportError:
        raise RuntimeError(
            "boto3 no está instalado. Ejecuta: pip install boto3"
        )

    account_id = os.getenv("R2_ACCOUNT_ID")
    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")

    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def _sanitize_filename(name: str) -> str:
    """
    Convierte un nombre arbitrario en un nombre de archivo seguro para R2.
    Ejemplo: 'Ingeniería de Sistemas' → 'ingenieria_de_sistemas'
    """
    # Normalizar caracteres con tilde
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
        'ñ': 'n', 'Ñ': 'N', 'ü': 'u', 'Ü': 'U',
    }
    for char, replacement in replacements.items():
        name = name.replace(char, replacement)

    # Convertir a minúsculas, reemplazar espacios por guión bajo
    name = name.lower().strip()
    name = re.sub(r'[\s\-]+', '_', name)
    # Eliminar caracteres no permitidos
    name = re.sub(r'[^a-z0-9_\.]', '', name)
    # Asegurar extensión .json
    if not name.endswith('.json'):
        name += '.json'
    return name


def _semester_label(periodo: str) -> str:
    """
    Genera un label legible para el selector de semestres.
    Ejemplo: "2026-1" → "2026 · Semestre 1"
    """
    try:
        year, sem = periodo.split("-")
        return f"{year} · Semestre {sem}"
    except ValueError:
        return periodo


def _get_global_index(client, bucket_name: str) -> dict:
    """
    Descarga el index.json global del bucket. Si no existe, retorna uno vacío.
    """
    try:
        response = client.get_object(Bucket=bucket_name, Key="index.json")
        raw = response["Body"].read().decode("utf-8")
        return json.loads(raw)
    except Exception as e:
        # boto3 lanza ClientError con código 'NoSuchKey' cuando el objeto no existe.
        # Capturamos cualquier excepción para ser resilientes (primer arranque, etc.)
        error_code = getattr(e, 'response', {}).get('Error', {}).get('Code', '') if hasattr(e, 'response') else ''
        if error_code in ('NoSuchKey', '404', 'NoSuchBucket'):
            logger.info("index.json no existe aún en el bucket. Se creará uno nuevo.")
        else:
            logger.warning(f"No se pudo leer index.json existente: {e}. Se creará uno nuevo.")
        return {"semestres": []}


def _put_global_index(client, bucket_name: str, index: dict) -> None:
    """
    Sube el index.json global al bucket (en la raíz).
    """
    index_bytes = json.dumps(index, ensure_ascii=False, indent=2).encode("utf-8")
    client.put_object(
        Bucket=bucket_name,
        Key="index.json",
        Body=index_bytes,
        ContentType="application/json; charset=utf-8",
        # Sin caché agresiva: la app siempre quiere el índice más fresco
        CacheControl="public, max-age=60, stale-while-revalidate=30",
    )
    logger.info("index.json actualizado correctamente.")


def _update_global_index(
    client,
    bucket_name: str,
    semester: str,
    program_id: str,
    program_name: str,
    filename: str,
    faculty: str = "",
) -> None:
    """
    Actualiza el index.json global en el bucket:
    - Añade el semestre si no existe.
    - Añade o actualiza el programa dentro del semestre.
    - Ordena los semestres del más reciente al más antiguo.

    Formato resultante del index.json:
    {
      "semestres": [
        {
          "periodo": "2026-1",
          "label": "2026 · Semestre 1",
          "programas": [
            {
              "id": "sistemas",
              "nombre": "Ingeniería de Sistemas",
              "archivo": "sistemas.xlsx.json",
              "facultad": "Ingeniería",
              "activo": true
            }
          ]
        }
      ]
    }
    """
    index = _get_global_index(client, bucket_name)

    # Buscar o crear el semestre en el índice
    semestre_entry = next(
        (s for s in index["semestres"] if s["periodo"] == semester), None
    )
    if semestre_entry is None:
        semestre_entry = {
            "periodo": semester,
            "label": _semester_label(semester),
            "programas": [],
        }
        index["semestres"].append(semestre_entry)

    # Buscar o crear el programa dentro del semestre
    programa_entry = next(
        (p for p in semestre_entry["programas"] if p["id"] == program_id), None
    )
    if programa_entry is None:
        semestre_entry["programas"].append({
            "id": program_id,
            "nombre": program_name,
            "archivo": filename,
            "facultad": faculty,
            "activo": True,
        })
    else:
        # Actualizar campos (por si cambian)
        programa_entry["nombre"] = program_name
        programa_entry["archivo"] = filename
        programa_entry["facultad"] = faculty
        programa_entry["activo"] = True

    # Ordenar semestres: más reciente primero (orden descendente alfanumérico)
    index["semestres"].sort(key=lambda s: s["periodo"], reverse=True)

    _put_global_index(client, bucket_name, index)


def upload_schedule_json(
    semester: str,
    filename: str,
    json_data: dict,
    program_id: str = "",
    program_name: str = "",
    faculty: str = "",
) -> str:
    """
    Sube un JSON de oferta académica a Cloudflare R2 y actualiza el índice global.

    Parámetros:
        semester     — Identificador del semestre (ej. "2026-1")
        filename     — Nombre original del archivo fuente (ej. "2026-1 Ing de Sistemas.xlsx")
                       Se limpiará automáticamente. Debe terminar en .xlsx.json o .json.
        json_data    — Diccionario Python con los datos del horario exportado
        program_id   — ID corto del programa (ej. "sistemas"). Si está vacío, se deriva del filename.
        program_name — Nombre legible del programa (ej. "Ingeniería de Sistemas").
                       Si está vacío, se toma de json_data["metadata"]["programa"].
        faculty      — Facultad del programa (ej. "Ingeniería").

    Retorna:
        La URL pública del archivo subido en R2.

    Lanza:
        RuntimeError si R2 no está configurado o falla la subida.
    """
    if not is_r2_configured():
        raise RuntimeError(
            "Cloudflare R2 no está configurado. "
            "Verifica las variables R2_* en el archivo .env del backend."
        )

    client = _get_r2_client()
    bucket_name = os.getenv("R2_BUCKET_NAME")
    public_url_base = os.getenv("R2_PUBLIC_URL", "").rstrip("/")

    safe_semester = re.sub(r'[^a-z0-9\-_]', '', semester.lower())
    safe_filename = _sanitize_filename(filename)

    object_key = f"{safe_semester}/{safe_filename}"

    # Derivar program_name y program_id si no se proveyeron
    if not program_name:
        program_name = json_data.get("metadata", {}).get("programa", filename)
    if not program_id:
        program_id = re.sub(r'[^a-z0-9_]', '', safe_filename.replace('.json', ''))

    json_bytes = json.dumps(json_data, ensure_ascii=False, indent=2).encode("utf-8")

    logger.info(f"Subiendo a R2: bucket={bucket_name}, key={object_key}, size={len(json_bytes)} bytes")

    client.put_object(
        Bucket=bucket_name,
        Key=object_key,
        Body=json_bytes,
        ContentType="application/json; charset=utf-8",
        # Cachear 1 hora en cliente; R2/Cloudflare sirve desde CDN automáticamente
        CacheControl="public, max-age=3600, stale-while-revalidate=60",
    )

    public_url = f"{public_url_base}/{object_key}"
    logger.info(f"Publicado exitosamente en R2: {public_url}")

    # Actualizar el índice global de semestres
    _update_global_index(
        client=client,
        bucket_name=bucket_name,
        semester=safe_semester,
        program_id=program_id,
        program_name=program_name,
        filename=safe_filename,
        faculty=faculty,
    )

    return public_url


def get_r2_index() -> dict:
    """
    Obtiene el index.json global desde el bucket de R2.
    """
    if not is_r2_configured():
        raise RuntimeError("Cloudflare R2 no está configurado.")
    client = _get_r2_client()
    bucket_name = os.getenv("R2_BUCKET_NAME")
    return _get_global_index(client, bucket_name)


def get_r2_object(semester: str, filename: str) -> dict:
    """
    Descarga y parsea un archivo JSON de oferta académica desde R2.
    """
    if not is_r2_configured():
        raise RuntimeError("Cloudflare R2 no está configurado.")
    client = _get_r2_client()
    bucket_name = os.getenv("R2_BUCKET_NAME")

    # Limpiar y sanitizar rutas
    safe_semester = re.sub(r'[^a-z0-9\-_]', '', semester.lower())
    safe_filename = _sanitize_filename(filename)
    object_key = f"{safe_semester}/{safe_filename}"

    logger.info(f"Descargando desde R2: bucket={bucket_name}, key={object_key}")
    response = client.get_object(Bucket=bucket_name, Key=object_key)
    raw = response["Body"].read().decode("utf-8")
    return json.loads(raw)

