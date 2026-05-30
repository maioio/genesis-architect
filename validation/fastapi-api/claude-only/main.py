from fastapi import FastAPI, HTTPException
from models import Task, TaskCreate, TaskUpdate
from typing import List
import uuid

app = FastAPI(title="Task Manager")

tasks_db: dict = {}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/tasks", response_model=Task)
def create_task(task: TaskCreate):
    task_id = str(uuid.uuid4())
    new_task = Task(id=task_id, **task.model_dump())
    tasks_db[task_id] = new_task
    return new_task

@app.get("/tasks", response_model=List[Task])
def list_tasks():
    return list(tasks_db.values())

@app.get("/tasks/{task_id}", response_model=Task)
def get_task(task_id: str):
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks_db[task_id]

@app.put("/tasks/{task_id}", response_model=Task)
def update_task(task_id: str, update: TaskUpdate):
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="Task not found")
    task = tasks_db[task_id]
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    tasks_db[task_id] = task
    return task

@app.delete("/tasks/{task_id}")
def delete_task(task_id: str):
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail="Task not found")
    del tasks_db[task_id]
    return {"deleted": task_id}
