from typing import List, Optional

from pydantic import BaseModel, EmailStr, HttpUrl


class QueueAuditRequest(BaseModel):
    url: HttpUrl
    email: EmailStr
    client_name: Optional[str] = None
    customer_id: Optional[str] = None
    urls: Optional[List[HttpUrl]] = None


class QueueAuditResponse(BaseModel):
    # Public token used for queue status polling.
    job_token: str
    status: str
    message: str
    audit_id: Optional[str] = None


class QueueStatusResponse(BaseModel):
    job_token: str
    status: str
    message: str
    estimated_wait_minutes: Optional[int] = None
    result_path: Optional[str] = None
