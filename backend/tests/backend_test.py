"""Backend API tests for academic schedule processor."""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://timetable-validator.preview.emergentagent.com').rstrip('/')
TEST_FILE = '/tmp/test_schedule.xlsx'


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    return s


@pytest.fixture(scope="module")
def schedule_id(api):
    """Upload file once and reuse across tests."""
    with open(TEST_FILE, 'rb') as f:
        files = {'file': ('sistemas-2026-1.xlsx', f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
        r = api.post(f"{BASE_URL}/api/upload", files=files, timeout=60)
    assert r.status_code == 200, f"Upload failed: {r.status_code} {r.text}"
    data = r.json()
    assert "schedule_id" in data
    assert "confianza_global" in data
    return data["schedule_id"]


# Health
def test_root(api):
    r = api.get(f"{BASE_URL}/api/", timeout=15)
    assert r.status_code == 200
    assert "message" in r.json()


# Subjects dictionary
def test_get_subjects(api):
    r = api.get(f"{BASE_URL}/api/subjects", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "id" in data[0] and "nombre_oficial" in data[0]


def test_search_subjects(api):
    r = api.get(f"{BASE_URL}/api/subjects/search/calculo", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


# Upload + process
def test_upload_and_processing(schedule_id):
    assert schedule_id and isinstance(schedule_id, str)


def test_upload_invalid_file(api):
    files = {'file': ('test.txt', b'hello', 'text/plain')}
    r = api.post(f"{BASE_URL}/api/upload", files=files, timeout=15)
    assert r.status_code == 400


# Get schedule
def test_get_schedule(api, schedule_id):
    r = api.get(f"{BASE_URL}/api/schedule/{schedule_id}", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == schedule_id
    assert "celdas" in data
    assert isinstance(data["celdas"], list)
    assert len(data["celdas"]) > 0


def test_get_schedule_not_found(api):
    r = api.get(f"{BASE_URL}/api/schedule/nonexistent-id", timeout=15)
    assert r.status_code == 404


def test_get_schedules_list(api, schedule_id):
    r = api.get(f"{BASE_URL}/api/schedules", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert any(s.get("id") == schedule_id for s in data)


# Update block
def test_update_block(api, schedule_id):
    r = api.get(f"{BASE_URL}/api/schedule/{schedule_id}", timeout=15)
    schedule = r.json()
    target = None
    for cell in schedule["celdas"]:
        if cell.get("bloques"):
            target = (cell["dia"], cell["hora_inicio"], cell["bloques"][0]["id"])
            break
    assert target is not None, "No block found to update"
    dia, hi, bid = target
    payload = {"materia": "TEST_Materia_Updated", "grupo": "G99", "docente": "TEST Docente", "aula": "A101"}
    r = api.put(f"{BASE_URL}/api/schedule/{schedule_id}/cell/{dia}/{hi}/block/{bid}", json=payload, timeout=15)
    assert r.status_code == 200, f"{r.status_code} {r.text}"

    # Verify persistence
    r2 = api.get(f"{BASE_URL}/api/schedule/{schedule_id}", timeout=15)
    sched = r2.json()
    found = False
    for cell in sched["celdas"]:
        if cell["dia"] == dia and cell["hora_inicio"] == hi:
            for b in cell["bloques"]:
                if b["id"] == bid:
                    assert b["materia"] == "TEST_Materia_Updated"
                    assert b["grupo"] == "G99"
                    assert b["estado"] == "confirmed"
                    found = True
    assert found


def test_update_block_not_found(api, schedule_id):
    r = api.put(f"{BASE_URL}/api/schedule/{schedule_id}/cell/Lunes/07:00/block/nonexistent",
                json={"materia": "X"}, timeout=15)
    assert r.status_code == 404


# Export
def test_export(api, schedule_id):
    r = api.post(f"{BASE_URL}/api/schedule/{schedule_id}/export", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, (dict, list))


# Delete block
def test_delete_block(api, schedule_id):
    r = api.get(f"{BASE_URL}/api/schedule/{schedule_id}", timeout=15)
    schedule = r.json()
    target = None
    for cell in schedule["celdas"]:
        if cell.get("bloques"):
            target = (cell["dia"], cell["hora_inicio"], cell["bloques"][0]["id"])
            break
    assert target is not None
    dia, hi, bid = target
    r = api.delete(f"{BASE_URL}/api/schedule/{schedule_id}/cell/{dia}/{hi}/block/{bid}", timeout=15)
    assert r.status_code == 200

    # Verify removed
    r2 = api.get(f"{BASE_URL}/api/schedule/{schedule_id}", timeout=15)
    sched = r2.json()
    for cell in sched["celdas"]:
        if cell["dia"] == dia and cell["hora_inicio"] == hi:
            assert all(b["id"] != bid for b in cell["bloques"])


def test_delete_block_not_found(api, schedule_id):
    r = api.delete(f"{BASE_URL}/api/schedule/{schedule_id}/cell/Lunes/07:00/block/nonexistent", timeout=15)
    assert r.status_code == 404
