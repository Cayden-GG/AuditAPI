import enum
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, HttpUrl, conlist
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
    tier = Column(String, default="free")
    status = Column(SQLEnum(AuditStatus), default=AuditStatus.PENDING)
    order_id = Column(String, nullable=True)
    callback_url = Column(String, nullable=True)
    social_links = Column(String, nullable=True)
    
    # Store links to your GCS Reports
    seo_report_url = Column(String, nullable=True)
    perf_report_url = Column(String, nullable=True)
    action_list_url = Column(String, nullable=True)
    seo_report_object = Column(String, nullable=True)
    perf_report_object = Column(String, nullable=True)
    key_findings_object = Column(String, nullable=True)
    accessibility_report_object = Column(String, nullable=True)
    audit_json_object = Column(String, nullable=True)
    ai_json_object = Column(String, nullable=True)
    audit_log_object = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class AuditCreate(BaseModel):
    url: HttpUrl
    email: EmailStr
    client_name: Optional[str] = None


class PaidAuditCreate(BaseModel):
    customer_name: Optional[str] = Field(None, alias="customerName")
    customer_email: EmailStr = Field(..., alias="customerEmail")
    website_url: HttpUrl = Field(..., alias="websiteUrl")
    social_links: conlist(str, min_length=0, max_length=3) = Field(..., alias="socialLinks")
    order_id: str = Field(..., alias="orderId")
    callback_url: HttpUrl = Field(..., alias="callbackUrl")

    class Config:
        allow_population_by_field_name = True


class AuditResponse(BaseModel):
    job_id: Optional[str] = None 
    job_token: str
    status: str
    message: str


class AuditResendRequest(BaseModel):
    job_id: Optional[str] = None
    target_url: Optional[HttpUrl] = None
    to_email: Optional[EmailStr] = None


class AuditResendResponse(BaseModel):
    status: str
    message: str
    job_id: Optional[str] = None
    target_url: Optional[str] = None
    resent_to: Optional[EmailStr] = None


class AuditRecord(BaseModel):
    id: str
    target_url: str
    client_email: str
    client_name: Optional[str] = None
    tier: Optional[str] = None
    status: AuditStatus
    order_id: Optional[str] = None
    callback_url: Optional[str] = None
    social_links: Optional[str] = None
    seo_report_url: Optional[str] = None
    perf_report_url: Optional[str] = None
    action_list_url: Optional[str] = None
    seo_report_object: Optional[str] = None
    perf_report_object: Optional[str] = None
    key_findings_object: Optional[str] = None
    accessibility_report_object: Optional[str] = None
    audit_json_object: Optional[str] = None
    ai_json_object: Optional[str] = None
    audit_log_object: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        orm_mode = True

class SendEmailRequest(BaseModel): 
    to_email: EmailStr
    send_email: EmailStr
    subject_line: str
    html_content: str
    attachments: Optional[str] = None

class SendEmailResponse(BaseModel): 
    status: str
    message: str
    sent_to: Optional[EmailStr] = None
