# Tests from PITFALLS.md Pitfall 4 - canary test catches silent async fixture failures
# If asyncio_mode is wrong, async fixtures silently don't run and tests pass vacuously
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_create_and_retrieve_exactly_one_task(client):
    """Canary: creates 1 task and asserts exactly 1 exists - fails if async fixtures silently skipped."""
    r = client.post("/tasks", json={"title": "Canary Task", "description": "Must exist"})
    assert r.status_code == 200
    task_id = r.json()["id"]

    r2 = client.get(f"/tasks/{task_id}")
    assert r2.status_code == 200
    assert r2.json()["title"] == "Canary Task"
    assert r2.json()["description"] == "Must exist", (
        "Task description not persisted - possible async session fixture failure"
    )
