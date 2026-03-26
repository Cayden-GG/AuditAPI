from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.emails.brevo_email import send_generic_email
from app.models import SendEmailRequest, SendEmailResponse

router = APIRouter()


@router.post("/api/sendEmail", response_model=SendEmailResponse)
def send_website_email(payload: SendEmailRequest):
    if not payload.to_email or not payload.html_content:
        raise HTTPException(status_code=400, detail="Provide to_email and html_content.")

    attachments = []
    if payload.attachments:
        for raw in payload.attachments.split(","):
            path = Path(raw.strip())
            if not path:
                continue
            if not path.exists():
                raise HTTPException(status_code=400, detail=f"Attachment not found: {path}")
            attachments.append(path)

    try:
        send_generic_email(
            to_email=payload.to_email,
            sender_email=payload.send_email,
            subject=payload.subject_line,
            html_content=payload.html_content,
            attachments=attachments or None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return SendEmailResponse(
        status="sent",
        message="Email sent.",
        sent_to=payload.to_email,
    )
