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
"""

import json
import logging
import os
import re

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


def upload_schedule_json(semester: str, filename: str, json_data: dict) -> str:
    """
    Sube un JSON de oferta académica a Cloudflare R2.

    Parámetros:
        semester  — Identificador del semestre (ej. "2026-1")
        filename  — Nombre del archivo sin extensión (ej. "ingenieria_de_sistemas")
        json_data — Diccionario Python con los datos del horario exportado

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

    return public_url
