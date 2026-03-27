from pathlib import Path
import os
import base64
from urllib import error, request
import json

from fastapi import APIRouter, HTTPException

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
        return BrevoListSignupResponse(
            status_code=500,
            message="Brevo not configured"
        )
    
    brevo_payload = {
        "email": payload.email, 
        "attributes": {
            "FIRSTNAME": payload.name.split(" ")[0],
            "LASTNAME": " ".join(payload.name.split(" ")[1:]) or ""
        },
        "listIds": [int(BREVO_NEWSLETTER_SIGNUP_LIST_ID)],
        "updateEnabled": True,
    }
    print(f"bp: {brevo_payload}")

    req = request.Request(
            BREVO_CONTACTS_URL,
            data=json.dumps(brevo_payload).encode("utf-8"),
            headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
            method="POST",
        )
        
    try:
        with request.urlopen(req, timeout=30) as response:
            if not response.ok:
                if response.code == "duplicate_parameter":
                    return BrevoListSignupResponse(
                        status_code=400,
                        message="Dulplicate contact entry",
                        data={"code": "duplicate_parameter"}
                    )

                raise RuntimeError(
                    f"Failed to add Brevo newsletter contact with status {response.status}"
                )
            else: 
                return BrevoListSignupResponse(
                    status_code="200",
                    message="Successfully subscribed new contact",
                )
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Brevo newsletter signup failed: {detail}") from exc


@router.post("/api/signupAuditList", response_model=BrevoListSignupResponse)
def audit_signup(payload: BrevoListSignupRequest):
    if not payload.email or not payload.name: 
        raise HTTPException(status_code=400, detail="Provide email and name.")

    BREVO_API_KEY = os.getenv("BREVO_API_KEY")
    BREVO_AUDIT_SIGNUP_LIST_ID = os.getenv("BREVO_AUDIT_SIGNUP_LIST_ID")
    if not BREVO_API_KEY or not BREVO_AUDIT_SIGNUP_LIST_ID:
        return BrevoListSignupResponse(
            status_code=500,
            message="Brevo not configured"
        )
    
    brevo_payload = {
        "email": payload.email, 
        "attributes": {
            "FIRSTNAME": payload.name.split(" ")[0],
            "LASTNAME": " ".join(payload.name.split(" ")[1:]) or ""
        },
        "listIds": [int(BREVO_AUDIT_SIGNUP_LIST_ID)],
        "updateEnabled": True,
    }
    print(brevo_payload)

    req = request.Request(
            BREVO_CONTACTS_URL,
            data=json.dumps(brevo_payload).encode("utf-8"),
            headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
            method="POST",
        )

    try:
        with request.urlopen(req, timeout=30) as response:
            if not response.ok:
                if response.code == "duplicate_parameter":
                    return BrevoListSignupResponse(
                        status_code=400,
                        message="Dulplicate contact entry",
                        data={"code": "duplicate_parameter"}
                    )

                raise RuntimeError(
                    f"Failed to add Brevo audit list contact with status {response.status}"
                )
            else: 
                return BrevoListSignupResponse(
                    status_code="200",
                    message="Successfully subscribed new contact",
                )
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Brevo audit list add failed: {detail}") from exc


