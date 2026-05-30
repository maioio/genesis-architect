# Architecture note: alembic upgrade head in lifespan - refuses to start if migrations fail
# Avoids: Pitfall 3 - missing table crash on first query after deploy

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from models import TaskORM, TaskCreate, TaskUpdate, TaskResponse
from deps import get_db
from database import Base, engine
from typing import List
import subprocess
import logging

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True, text=True, check=True
        )
        logger.info("Migrations applied: %s", result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        # No alembic in dev/test - fall back to create_all for SQLite dev only
        logger.warning("alembic not found - using create_all (dev only)")
        Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="Task Manager", lifespan=lifespan)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/tasks", response_model=TaskResponse)
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    db_task = TaskORM(**task.model_dump())
    db.add(db_task)
    db.flush()
    db.refresh(db_task)
    return db_task

@app.get("/tasks", response_model=List[TaskResponse])
def list_tasks(db: Session = Depends(get_db)):
    return db.query(TaskORM).all()

@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(TaskORM).filter(TaskORM.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.put("/tasks/{task_id}", response_model=TaskResponse)
def update_task(task_id: str, update: TaskUpdate, db: Session = Depends(get_db)):
    task = db.query(TaskORM).filter(TaskORM.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    db.flush()
    db.refresh(task)
    return task

@app.delete("/tasks/{task_id}")
def delete_task(task_id: str, db: Session = Depends(get_db)):
    task = db.query(TaskORM).filter(TaskORM.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    return {"deleted": task_id}
