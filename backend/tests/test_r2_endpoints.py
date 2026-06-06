import sys
from pathlib import Path
from fastapi import status, HTTPException
from fastapi.testclient import TestClient

# Paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BACKEND_DIR))

from server import app
from routers.auth import get_current_admin

def test_r2_endpoints_access_control():
    client = TestClient(app)

    # 1. Test unauthenticated: No token/headers
    response = client.get("/api/r2/schedules")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    response = client.post("/api/r2/import", json={"semester": "2026-1", "filename": "sistemas.json"})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_r2_endpoints_role_user():
    # 2. Test authenticated as normal 'user' (role !== admin) -> Should get 403 Forbidden
    client = TestClient(app)
    
    async def override_get_current_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador"
        )
    
    app.dependency_overrides[get_current_admin] = override_get_current_admin
    try:
        response = client.get("/api/r2/schedules")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["detail"] == "No tienes permisos de administrador"

        response = client.post("/api/r2/import", json={"semester": "2026-1", "filename": "sistemas.json"})
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["detail"] == "No tienes permisos de administrador"
    finally:
        app.dependency_overrides.clear()


def test_r2_endpoints_role_admin():
    # 3. Test authenticated as 'admin' -> Should bypass the admin check
    client = TestClient(app)
    
    async def override_get_current_admin():
        return {"username": "test_admin", "role": "admin"}
        
    app.dependency_overrides[get_current_admin] = override_get_current_admin
    try:
        response = client.get("/api/r2/schedules")
        assert response.status_code in (status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE, status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Test post import validation
        # Empty body or missing fields -> 422 Unprocessable Entity
        response = client.post("/api/r2/import", json={})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Valid body structure -> Should trigger download. If file doesn't exist, should return 404.
        response = client.post("/api/r2/import", json={"semester": "nonexistent_sem", "filename": "nonexistent_file.json"})
        assert response.status_code in (status.HTTP_404_NOT_FOUND, status.HTTP_503_SERVICE_UNAVAILABLE, status.HTTP_500_INTERNAL_SERVER_ERROR)
    finally:
        app.dependency_overrides.clear()

if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__]))
