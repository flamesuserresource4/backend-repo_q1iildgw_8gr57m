"""
Database Schemas for SkillSwap

Each Pydantic model represents a collection in MongoDB. The collection name is the
lowercase of the class name (e.g., User -> "user").
"""

from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal
from datetime import datetime


class AvailabilitySlot(BaseModel):
    day: Literal[
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    slots: List[str] = Field(default_factory=list, description="List of time ranges, e.g., ['10:00-11:00']")


class User(BaseModel):
    email: EmailStr
    password_hash: str
    name: str
    age: Optional[int] = Field(None, ge=13, le=120)
    city: Optional[str] = None
    teach_skills: List[str] = Field(default_factory=list)
    learn_skills: List[str] = Field(default_factory=list)
    availability: List[AvailabilitySlot] = Field(default_factory=list)

    coins: int = 20
    rating_avg: float = 0.0
    rating_count: int = 0
    badges: List[str] = Field(default_factory=list)

    teaching_sessions: int = 0
    learning_sessions: int = 0

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Chat(BaseModel):
    members: List[str]  # [user_id_1, user_id_2]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Message(BaseModel):
    chat_id: str
    sender_id: str
    text: str
    created_at: Optional[datetime] = None


class Session(BaseModel):
    chat_id: str
    teacher_id: str
    learner_id: str
    duration: Literal[30, 60]
    scheduled_time: str  # ISO datetime string for simplicity
    status: Literal["scheduled", "completed", "cancelled"] = "scheduled"
    meet_link: Optional[str] = None
    zoom_link: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Rating(BaseModel):
    session_id: str
    rater_id: str
    ratee_id: str
    score: int = Field(ge=1, le=5)
    feedback: Optional[str] = None
    created_at: Optional[datetime] = None
