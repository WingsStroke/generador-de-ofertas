import re
from pathlib import Path

backend_dir = Path(r"c:\Users\redbo\Downloads\Angel\proyectos\Generador-de-ofertas\backend")
server_py = backend_dir / "server.py"

with open(server_py, "r", encoding="utf-8") as f:
    content = f.read()

# Buscamos desde @api_router.get("/schedules") hasta el final o antes de @api_router.get("/subjects")
start_idx = content.find('@api_router.get("/schedules")')
end_idx = content.find('@api_router.get("/subjects"', start_idx)

schedules_content = content[start_idx:end_idx]
schedules_content = schedules_content.replace("@api_router", "@router")

header = """from fastapi import APIRouter, HTTPException, Request
from typing import Dict, List, Any
from models import BlockUpdate, BulkBlockUpdate, BlockCreate, BlockMove
from state import limiter, programas_dict
from storage import storage
from datetime import datetime, timezone
import uuid
from utils.schedule_helpers import (
    _atomic_update_with_retry,
    _add_audit_log,
    _iter_celdas_collections,
    _update_block_in_schedule,
    _delete_block_from_schedule,
    _find_block_locations
)
from utils.export_helper import export_to_json_format

router = APIRouter(tags=["Schedules"])

"""

with open(backend_dir / "routers" / "schedules.py", "w", encoding="utf-8") as f:
    f.write(header + schedules_content)
