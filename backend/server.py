from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

from state import limiter
from storage import storage
from utils.program_loader import load_academic_programs

from routers.programs import router as programs_router
from routers.teachers import router as teachers_router
from routers.upload import router as upload_router
from routers.schedules import router as schedules_router
from routers.collab import router as collab_router
from routers.auth import router as auth_router
from routers.r2 import router as r2_router
from database import init_db, close_db

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

load_academic_programs(ROOT_DIR)

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(programs_router, prefix="/api")
app.include_router(teachers_router, prefix="/api")
app.include_router(upload_router, prefix="/api")
app.include_router(schedules_router, prefix="/api")
app.include_router(collab_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(r2_router, prefix="/api")

@app.get("/api/")
async def root():
    from state import programas_dict
    return {"message": "Academic Schedule Processor API", "programs": len(programas_dict)}

@app.on_event("startup")
async def startup_event():
    await init_db()
    storage.start_cleanup()
    logger.info("Storage cleanup task iniciado")

@app.on_event("shutdown")
async def shutdown_db_client():
    await close_db()
    await storage.close()
    logger.info("Storage cerrado correctamente")
