from pydantic import BaseModel
from typing import Optional
from enum import Enum

class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"

class TaskCreate(BaseModel):
    title: str
    description: str = ""
    priority: Priority = Priority.medium
    done: bool = False

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[Priority] = None
    done: Optional[bool] = None

class Task(BaseModel):
    id: str
    title: str
    description: str = ""
    priority: Priority = Priority.medium
    done: bool = False
