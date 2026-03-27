from pathlib import Path
import os
import base64
from urllib import error, request
import json

from fastapi import APIRouter, HTTPException, status

from ..models import BrevoListSignupRequest, BrevoListSignupResponse 

router = APIRouter()

BREVO_CONTACTS_URL = "https://api.brevo.com/v3/contacts"

@router.post("/api/signupNewsletter", response_model=BrevoListSignupResponse)
def signup_newsletter(payload: BrevoListSignupRequest): 
    if not payload.name or not payload.email:
        raise HTTPException(status_code=400, detail="Provide email and name.")
    
    BREVO_API_KEY = os.getenv("BREVO_API_KEY")
    BREVO_NEWSLETTER_SIGNUP_LIST_ID = os.getenv("BREVO_NEWSLETTER_SIGNUP_LIST_ID")
    if not BREVO_API_KEY or not BREVO_NEWSLETTER_SIGNUP_LIST_ID:
        raise HTTPException(status_code=500, detail="Brevo keys not configured.")

    
    brevo_payload = {
        "email": payload.email, 
        "attributes": {
            "FIRSTNAME": payload.name.split(" ")[0],
            "LASTNAME": " ".join(payload.name.split(" ")[1:]) or ""
        },
        "listIds": [int(BREVO_NEWSLETTER_SIGNUP_LIST_ID)],
    }

    req = request.Request(
            BREVO_CONTACTS_URL,
            data=json.dumps(brevo_payload).encode("utf-8"),
            headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
            method="POST",
        )
        
    try:
        with request.urlopen(req, timeout=30) as response:
            if response.status == 201:
                return BrevoListSignupResponse(
                    status_code="200",
                    message="Successfully subscribed new contact",
                )
                
    except error.HTTPError as exc:
        try:
            error_content = json.loads(exc.read().decode())
            brevo_code = error_content.get("code")
            brevo_message = error_content.get("message")
        except Exception:
            brevo_code = None
            brevo_message = str(exc)

        if brevo_code == "duplicate_parameter":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={ 
                    "message": "Dulplicate contact entry",
                    "code": "duplicate_parameter",
                }
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to add Brevo newsletter contact: {brevo_message}"
        )


@router.post("/api/signupAuditList", response_model=BrevoListSignupResponse)
def audit_signup(payload: BrevoListSignupRequest):
    if not payload.email or not payload.name: 
        raise HTTPException(status_code=400, detail="Provide email and name.")

    BREVO_API_KEY = os.getenv("BREVO_API_KEY")
    BREVO_AUDIT_SIGNUP_LIST_ID = os.getenv("BREVO_AUDIT_SIGNUP_LIST_ID")
    if not BREVO_API_KEY or not BREVO_AUDIT_SIGNUP_LIST_ID:
        raise HTTPException(status_code=500, detail="Brevo keys not configured.")
    
    brevo_payload = {
        "email": payload.email, 
        "attributes": {
            "FIRSTNAME": payload.name.split(" ")[0],
            "LASTNAME": " ".join(payload.name.split(" ")[1:]) or ""
        },
        "listIds": [int(BREVO_AUDIT_SIGNUP_LIST_ID)],
        "updateEnabled": True,
    }

    req = request.Request(
            BREVO_CONTACTS_URL,
            data=json.dumps(brevo_payload).encode("utf-8"),
            headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
            method="POST",
        )

    try:
        with request.urlopen(req, timeout=30) as response:
            if response.status == 201:
                return BrevoListSignupResponse(
                    status_code="200",
                    message="Successfully subscribed new contact",
                )
                
    except error.HTTPError as exc:
        try:
            error_content = json.loads(exc.read().decode())
            brevo_code = error_content.get("code")
            brevo_message = error_content.get("message")
        except Exception:
            brevo_code = None
            brevo_message = str(exc)

        if brevo_code == "duplicate_parameter":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={ 
                    "message": "Dulplicate contact entry",
                    "code": "duplicate_parameter",
                }
            )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to add Brevo audit contact: {brevo_message}"
        )

