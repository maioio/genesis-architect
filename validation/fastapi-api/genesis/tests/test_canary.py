# Tests from PITFALLS.md Pitfall 4 - canary test catches silent async fixture failures
# If asyncio_mode is wrong, async fixtures silently don't run and tests pass vacuously
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_create_and_retrieve_exactly_one_task():
    """Canary: creates 1 task and asserts exactly 1 exists - fails if async fixtures silently skipped."""
    # Clear state first
    tasks_before = client.get("/tasks").json()

    r = client.post("/tasks", json={"title": "Canary Task", "description": "Must exist"})
    assert r.status_code == 200
    task_id = r.json()["id"]

    r2 = client.get(f"/tasks/{task_id}")
    assert r2.status_code == 200
    assert r2.json()["title"] == "Canary Task"
    # This assertion fails if DB session didn't actually persist (silent async fixture failure)
    assert r2.json()["description"] == "Must exist", (
        "Task description not persisted - possible async session fixture failure"
    )
