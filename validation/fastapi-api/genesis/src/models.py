from sqlalchemy import Column, String, Boolean, Enum as SAEnum
from sqlalchemy.dialects.sqlite import TEXT
from database import Base
from pydantic import BaseModel
from typing import Optional
from enum import Enum
import uuid

class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"

class TaskORM(Base):
    __tablename__ = "tasks"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(200), nullable=False)
    description = Column(TEXT, default="")
    priority = Column(SAEnum(Priority), default=Priority.medium)
    done = Column(Boolean, default=False)

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

class TaskResponse(BaseModel):
    id: str
    title: str
    description: str
    priority: Priority
    done: bool

    model_config = {"from_attributes": True}
