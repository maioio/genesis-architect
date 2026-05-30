from fastapi.testclient import TestClient
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from main import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200

def test_create_task():
    r = client.post("/tasks", json={"title": "Buy milk", "description": "2%"})
    assert r.status_code == 200
    assert r.json()["title"] == "Buy milk"

def test_list_tasks():
    client.post("/tasks", json={"title": "Task A"})
    r = client.get("/tasks")
    assert r.status_code == 200
    assert len(r.json()) >= 1

def test_get_task_not_found():
    r = client.get("/tasks/nonexistent-id")
    assert r.status_code == 404

def test_update_task():
    r = client.post("/tasks", json={"title": "Original"})
    task_id = r.json()["id"]
    r2 = client.put(f"/tasks/{task_id}", json={"title": "Updated"})
    assert r2.json()["title"] == "Updated"

def test_delete_task():
    r = client.post("/tasks", json={"title": "Delete me"})
    task_id = r.json()["id"]
    client.delete(f"/tasks/{task_id}")
    r2 = client.get(f"/tasks/{task_id}")
    assert r2.status_code == 404
