from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from database import db_instance
from utils.auth_helper import verify_password, create_access_token, decode_access_token

router = APIRouter(tags=["Authentication"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

class Token(BaseModel):
    access_token: str
    token_type: str
    username: str
    role: str

class LoginRequest(BaseModel):
    username: str
    password: str

async def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username = payload.get("sub")
    role = payload.get("role", "user")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no contiene identidad",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"username": username, "role": role}

async def get_current_admin(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador",
        )
    return current_user

@router.post("/auth/login", response_model=Token)
async def login(req: LoginRequest):
    if db_instance.users is None:
        raise HTTPException(status_code=500, detail="Error de conexión a la base de datos")
        
    user = await db_instance.users.find_one({"username": req.username})
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nombre de usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    role = user.get("role", "user")
    access_token = create_access_token(data={"sub": user["username"], "role": role})
    return {"access_token": access_token, "token_type": "bearer", "username": user["username"], "role": role}

@router.get("/auth/me")
async def read_users_me(current_user: dict = Depends(get_current_user)):
    return current_user
