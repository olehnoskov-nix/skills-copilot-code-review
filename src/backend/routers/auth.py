"""
Authentication endpoints for the High School Management System API
"""

from datetime import datetime, timedelta, timezone
import secrets
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..database import (
    auth_sessions_collection,
    teachers_collection,
    verify_password,
)

router = APIRouter(
    prefix="/auth",
    tags=["auth"]
)


SESSION_COOKIE = "mergington_session"
SESSION_TTL = timedelta(days=7)


def _secure_cookie(request: Request) -> bool:
    return request.url.scheme == "https" or request.url.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }


def get_authenticated_teacher(request: Request) -> Dict[str, Any]:
    """Return the teacher associated with the server-validated session cookie."""
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    session = auth_sessions_collection.find_one({
        "_id": session_id,
        "expires_at": {"$gt": datetime.now(timezone.utc)},
    })
    if not session:
        raise HTTPException(status_code=401, detail="Authentication required")

    teacher = teachers_collection.find_one({"_id": session["username"]})
    if not teacher:
        raise HTTPException(status_code=401, detail="Authentication required")
    return teacher


@router.post("/login")
def login(
    username: str,
    password: str,
    request: Request,
    response: Response,
) -> Dict[str, Any]:
    """Login a teacher account"""
    # Find the teacher in the database
    teacher = teachers_collection.find_one({"_id": username})

    # Verify password using Argon2 verifier from database.py
    if not teacher or not verify_password(teacher.get("password", ""), password):
        raise HTTPException(
            status_code=401, detail="Invalid username or password")

    prior_session = request.cookies.get(SESSION_COOKIE)
    if prior_session:
        auth_sessions_collection.delete_one({"_id": prior_session})

    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + SESSION_TTL
    auth_sessions_collection.insert_one({
        "_id": session_id,
        "username": teacher["username"],
        "expires_at": expires_at,
    })
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        httponly=True,
        secure=_secure_cookie(request),
        samesite="lax",
        max_age=int(SESSION_TTL.total_seconds()),
    )

    # Return teacher information (excluding password)
    return {
        "username": teacher["username"],
        "display_name": teacher["display_name"],
        "role": teacher["role"]
    }


@router.get("/check-session")
def check_session(
    teacher: Dict[str, Any] = Depends(get_authenticated_teacher),
) -> Dict[str, Any]:
    """Return teacher information for a valid server-side session."""

    return {
        "username": teacher["username"],
        "display_name": teacher["display_name"],
        "role": teacher["role"]
    }


@router.post("/logout")
def logout(request: Request, response: Response) -> Dict[str, str]:
    """Revoke the current session and clear its cookie."""
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        auth_sessions_collection.delete_one({"_id": session_id})
    response.delete_cookie(
        key=SESSION_COOKIE,
        httponly=True,
        secure=_secure_cookie(request),
        samesite="lax",
    )
    return {"message": "Logged out"}
