import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import User, AvailabilitySlot, Chat, Message, Session, Rating

app = FastAPI(title="SkillSwap API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Utility helpers

def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid object id")


def now_utc():
    return datetime.now(timezone.utc)


# Basic health

@app.get("/")
def root():
    return {"message": "SkillSwap Backend Running"}


@app.get("/test")
def test_database():
    info = {
        "backend": "✅ Running",
        "database": "❌ Not Connected",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "collections": [],
    }
    try:
        if db is None:
            return info
        info["database"] = "✅ Connected"
        info["collections"] = db.list_collection_names()
        return info
    except Exception as e:
        info["database"] = f"⚠️ Error: {str(e)[:80]}"
        return info


# Auth & onboarding

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    user_id: str
    email: EmailStr


@app.post("/auth/register", response_model=AuthResponse)
def register(req: RegisterRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    existing = db["user"].find_one({"email": req.email})
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    # NOTE: For MVP, store a simple hash placeholder (not production secure)
    password_hash = f"mvp::{req.password}"

    user = User(
        email=req.email,
        password_hash=password_hash,
        name="",
        age=None,
        city=None,
        teach_skills=[],
        learn_skills=[],
        availability=[],
        coins=20,
        rating_avg=0.0,
        rating_count=0,
        badges=[],
        teaching_sessions=0,
        learning_sessions=0,
        created_at=now_utc(),
        updated_at=now_utc(),
    )

    inserted_id = db["user"].insert_one(user.model_dump()).inserted_id
    return AuthResponse(user_id=str(inserted_id), email=req.email)


@app.post("/auth/login", response_model=AuthResponse)
def login(req: LoginRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    user = db["user"].find_one({"email": req.email})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if user.get("password_hash") != f"mvp::{req.password}":
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return AuthResponse(user_id=str(user["_id"]), email=req.email)


# Onboarding / profile setup

class ProfileUpdate(BaseModel):
    name: str
    age: Optional[int] = None
    city: Optional[str] = None
    teach_skills: List[str] = []
    learn_skills: List[str] = []
    availability: List[AvailabilitySlot] = []


@app.put("/profile/{user_id}")
def update_profile(user_id: str, body: ProfileUpdate):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    res = db["user"].update_one(
        {"_id": oid(user_id)},
        {"$set": {
            "name": body.name,
            "age": body.age,
            "city": body.city,
            "teach_skills": body.teach_skills,
            "learn_skills": body.learn_skills,
            "availability": [slot.model_dump() for slot in body.availability],
            "updated_at": now_utc(),
        }}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    doc = db["user"].find_one({"_id": oid(user_id)})
    doc["_id"] = str(doc["_id"])
    return doc


@app.get("/profile/{user_id}")
def get_profile(user_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    doc = db["user"].find_one({"_id": oid(user_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="User not found")
    doc["_id"] = str(doc["_id"])
    return doc


# Smart matchmaking

@app.get("/matches/{user_id}")
def find_matches(user_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    me = db["user"].find_one({"_id": oid(user_id)})
    if not me:
        raise HTTPException(status_code=404, detail="User not found")

    teach = set(me.get("teach_skills", []))
    learn = set(me.get("learn_skills", []))

    candidates = db["user"].find({"_id": {"$ne": oid(user_id)}})
    results = []
    for c in candidates:
        c_teach = set(c.get("teach_skills", []))
        c_learn = set(c.get("learn_skills", []))
        if (learn & c_teach) and (teach & c_learn):
            results.append({
                "user_id": str(c["_id"]),
                "name": c.get("name", ""),
                "city": c.get("city"),
                "age": c.get("age"),
                "teach_skills": list(c_teach),
                "learn_skills": list(c_learn),
                "match_for_me": list(learn & c_teach),
                "match_for_them": list(teach & c_learn),
                "rating_avg": c.get("rating_avg", 0),
            })
    return {"matches": results}


# Chat + messages

class EnsureChatRequest(BaseModel):
    user_a: str
    user_b: str


@app.post("/chat/ensure")
def ensure_chat(req: EnsureChatRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    members_sorted = sorted([req.user_a, req.user_b])
    existing = db["chat"].find_one({"members": members_sorted})
    if existing:
        return {"chat_id": str(existing["_id"]) }
    chat = Chat(members=members_sorted, created_at=now_utc(), updated_at=now_utc())
    cid = db["chat"].insert_one(chat.model_dump()).inserted_id
    return {"chat_id": str(cid)}


class SendMessageRequest(BaseModel):
    chat_id: str
    sender_id: str
    text: str


@app.post("/chat/send")
def send_message(req: SendMessageRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    msg = Message(chat_id=req.chat_id, sender_id=req.sender_id, text=req.text, created_at=now_utc())
    db["message"].insert_one(msg.model_dump())
    db["chat"].update_one({"_id": oid(req.chat_id)}, {"$set": {"updated_at": now_utc()}})
    return {"ok": True}


@app.get("/chat/messages/{chat_id}")
def get_messages(chat_id: str, limit: int = 100):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    msgs = list(db["message"].find({"chat_id": chat_id}).sort("created_at", 1).limit(limit))
    for m in msgs:
        m["_id"] = str(m["_id"])
    return {"messages": msgs}


# Scheduling sessions

class ScheduleRequest(BaseModel):
    chat_id: str
    teacher_id: str
    learner_id: str
    duration: int
    scheduled_time: str
    meet_link: Optional[str] = None
    zoom_link: Optional[str] = None


@app.post("/sessions/schedule")
def schedule_session(req: ScheduleRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    if req.duration not in (30, 60):
        raise HTTPException(status_code=400, detail="Invalid duration")
    sess = Session(
        chat_id=req.chat_id,
        teacher_id=req.teacher_id,
        learner_id=req.learner_id,
        duration=req.duration,  # type: ignore
        scheduled_time=req.scheduled_time,
        meet_link=req.meet_link,
        zoom_link=req.zoom_link,
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    sid = db["session"].insert_one(sess.model_dump()).inserted_id
    return {"session_id": str(sid)}


@app.get("/sessions/{user_id}")
def list_sessions(user_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    sessions = list(db["session"].find({"$or": [{"teacher_id": user_id}, {"learner_id": user_id}]}).sort("created_at", -1))
    for s in sessions:
        s["_id"] = str(s["_id"])
    return {"sessions": sessions}


# Ratings + coins

class RatingRequest(BaseModel):
    session_id: str
    rater_id: str
    ratee_id: str
    score: int
    feedback: Optional[str] = None


@app.post("/sessions/rate")
def rate_session(req: RatingRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    if not (1 <= req.score <= 5):
        raise HTTPException(status_code=400, detail="Score must be 1-5")

    session_doc = db["session"].find_one({"_id": oid(req.session_id)})
    if not session_doc:
        raise HTTPException(status_code=404, detail="Session not found")

    rating = Rating(
        session_id=req.session_id,
        rater_id=req.rater_id,
        ratee_id=req.ratee_id,
        score=req.score,
        feedback=req.feedback,
        created_at=now_utc(),
    )
    db["rating"].insert_one(rating.model_dump())

    # Update ratee rating
    u = db["user"].find_one({"_id": oid(req.ratee_id)})
    if u:
        count = int(u.get("rating_count", 0)) + 1
        avg = float(u.get("rating_avg", 0.0))
        new_avg = ((avg * (count - 1)) + req.score) / count
        db["user"].update_one({"_id": oid(req.ratee_id)}, {"$set": {"rating_avg": new_avg, "rating_count": count}})

    # Coins logic
    teacher_id = session_doc.get("teacher_id")
    learner_id = session_doc.get("learner_id")
    if teacher_id and learner_id:
        db["user"].update_one({"_id": oid(teacher_id)}, {"$inc": {"coins": 10, "teaching_sessions": 1}})
        db["user"].update_one({"_id": oid(learner_id)}, {"$inc": {"coins": -10, "learning_sessions": 1}})

    # Mark session completed
    db["session"].update_one({"_id": oid(req.session_id)}, {"$set": {"status": "completed", "updated_at": now_utc()}})

    # Badges
    t = db["user"].find_one({"_id": oid(teacher_id)}) if teacher_id else None
    if t:
        badges = set(t.get("badges", []))
        if int(t.get("teaching_sessions", 0)) >= 10:
            badges.add("Top Mentor")
        if int(t.get("learning_sessions", 0)) + int(t.get("teaching_sessions", 0)) >= 5:
            badges.add("Skill Streak")
        if float(t.get("rating_avg", 0)) > 4.5:
            badges.add("Helpful Teacher")
        db["user"].update_one({"_id": t["_id"]}, {"$set": {"badges": list(badges)}})

    return {"ok": True}


# Leaderboard

@app.get("/leaderboard")
def leaderboard():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    top = list(db["user"].find().sort("teaching_sessions", -1).limit(20))
    for u in top:
        u["_id"] = str(u["_id"])
    return {"top": top}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
