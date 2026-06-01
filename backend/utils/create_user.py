import sys
import os
import asyncio
import argparse
from datetime import datetime, timezone

# Añadir el backend al path para poder importar módulos desde la raíz del backend
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent.parent / '.env')

from database import db_instance, init_db, close_db
from utils.auth_helper import get_password_hash

async def create_user(username, password):
    await init_db()
    
    if db_instance.users is None:
        print("Error: No se pudo conectar a la base de datos.")
        await close_db()
        return

    # Comprobar si ya existe el usuario
    existing_user = await db_instance.users.find_one({"username": username})
    if existing_user:
        print(f"Error: El usuario '{username}' ya existe.")
        await close_db()
        return

    # Crear usuario
    hashed_password = get_password_hash(password)
    user_doc = {
        "username": username,
        "password_hash": hashed_password,
        "created_at": datetime.now(timezone.utc)
    }
    
    await db_instance.users.insert_one(user_doc)
    print(f"Éxito: Usuario '{username}' creado correctamente.")
    
    await close_db()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crear un usuario administrativo en MongoDB")
    parser.add_argument("--username", required=True, help="Nombre de usuario")
    parser.add_argument("--password", required=True, help="Contraseña segura")
    args = parser.parse_args()
    
    asyncio.run(create_user(args.username, args.password))
