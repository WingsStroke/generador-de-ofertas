import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path

# Cargar variables de entorno desde .env si existe en el mismo directorio
load_dotenv(Path(__file__).parent / '.env')

logger = logging.getLogger(__name__)

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "academic_schedules")

class Database:
    client: AsyncIOMotorClient = None
    db = None
    users = None

db_instance = Database()

async def init_db():
    try:
        db_instance.client = AsyncIOMotorClient(MONGO_URL)
        db_instance.db = db_instance.client[DB_NAME]
        db_instance.users = db_instance.db["users"]
        
        # Test connection
        await db_instance.client.admin.command('ping')
        logger.info(f"Conectado a MongoDB en {MONGO_URL} (BD: {DB_NAME})")
        
        # Crear índice único para usernames para evitar duplicados
        await db_instance.users.create_index("username", unique=True)
    except Exception as e:
        logger.error(f"Error conectando a MongoDB: {e}")

async def close_db():
    if db_instance.client:
        db_instance.client.close()
