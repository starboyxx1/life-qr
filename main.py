from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, String, Integer, Text, ForeignKey, DateTime
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from pydantic import BaseModel, Field
import uuid
import datetime
from typing import List, Optional
import os
import qrcode
from io import BytesIO
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, RedirectResponse

import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./lifeqr.db")

# Fix postgres:// → postgresql:// if needed
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, connect_args={} if DATABASE_URL.startswith("postgresql") else {"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()  # ← THIS LINE IS MISSING

class DBUser(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    age = Column(Integer)
    gender = Column(String)
    blood_group = Column(String)
    address = Column(String)
    emergency_contact_1 = Column(String)
    emergency_contact_2 = Column(String)
    doctor_name = Column(String)
    doctor_phone = Column(String)
    allergies = Column(Text)
    medications = Column(Text)
    medical_conditions = Column(Text)
    notes = Column(Text)

class DBScanHistory(Base):
    __tablename__ = "scan_history"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"))
    scanned_at = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="LifeQR API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic Models
class UserCreate(BaseModel):
    full_name: str
    age: int
    gender: str
    blood_group: str
    address: Optional[str] = None
    emergency_contact_1: str
    emergency_contact_2: Optional[str] = None
    doctor_name: Optional[str] = None
    doctor_phone: Optional[str] = None
    allergies: Optional[str] = None
    medications: Optional[str] = None
    medical_conditions: Optional[str] = None
    notes: Optional[str] = None

class UserResponse(UserCreate):
    id: str

@app.post("/api/users", response_model=UserResponse)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    user_id = str(uuid.uuid4())
    db_user = DBUser(id=user_id, **user.model_dump())
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.get("/api/users/{user_id}", response_model=UserResponse)
def get_user(user_id: str, db: Session = Depends(get_db)):
    user = db.query(DBUser).filter(DBUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Record scan history
    scan = DBScanHistory(user_id=user_id)
    db.add(scan)
    db.commit()
    
    return user

@app.get("/api/users/{user_id}/qr")
def generate_qr(user_id: str, request: Request):
    base_url = str(request.base_url)
    frontend_url = f"{base_url}app/profile.html?id={user_id}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(frontend_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

@app.get("/api/users/{user_id}/history")
def get_scan_history(user_id: str, db: Session = Depends(get_db)):
    history = db.query(DBScanHistory).filter(DBScanHistory.user_id == user_id).order_by(DBScanHistory.scanned_at.desc()).all()
    return [{"scanned_at": h.scanned_at} for h in history]

@app.get("/")
def root():
    return RedirectResponse(url="/app/index.html")

# Serve frontend files
frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
# frontend_dir = os.path.join(os.path.dirname(__file__), "../frontend")
app.mount("/app", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
