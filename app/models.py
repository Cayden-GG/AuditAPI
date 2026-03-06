import enum
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, HttpUrl
from sqlalchemy import Column, DateTime, Enum as SQLEnum, String

from .database import Base

class AuditStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class AuditTable(Base):
    __tablename__ = "audits"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    target_url = Column(String)
    client_email = Column(String, index=True)
    client_name = Column(String)
    status = Column(SQLEnum(AuditStatus), default=AuditStatus.PENDING)
    
    # Store links to your GCS Reports
    seo_report_url = Column(String, nullable=True)
    perf_report_url = Column(String, nullable=True)
    action_list_url = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class AuditCreate(BaseModel):
    url: HttpUrl
    email: EmailStr
    client_name: Optional[str] = None


class AuditResponse(BaseModel):
    job_id: str
    status: str
    message: str


class AuditRecord(BaseModel):
    id: str
    target_url: str
    client_email: str
    client_name: Optional[str] = None
    status: AuditStatus
    seo_report_url: Optional[str] = None
    perf_report_url: Optional[str] = None
    action_list_url: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        orm_mode = True
