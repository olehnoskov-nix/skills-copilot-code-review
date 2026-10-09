"""Announcement endpoints for public display and authenticated management."""

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..database import announcements_collection
from .auth import get_authenticated_teacher

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"],
)


class AnnouncementInput(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    message: str = Field(..., min_length=1, max_length=1000)
    start_date: Optional[date] = None
    expiration_date: date


def _announcement_data(announcement: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a MongoDB document to a JSON-safe announcement."""
    return {
        "id": announcement["_id"],
        "title": announcement["title"],
        "message": announcement["message"],
        "start_date": announcement.get("start_date"),
        "expiration_date": announcement["expiration_date"],
    }


def _validated_data(announcement: AnnouncementInput) -> Dict[str, Any]:
    title = announcement.title.strip()
    message = announcement.message.strip()
    if not title or not message:
        raise HTTPException(status_code=422, detail="Title and message are required")

    today = datetime.now(timezone.utc).date()
    if announcement.expiration_date < today:
        raise HTTPException(
            status_code=422,
            detail="Expiration date must be today or later",
        )
    if (
        announcement.start_date is not None
        and announcement.start_date > announcement.expiration_date
    ):
        raise HTTPException(
            status_code=422,
            detail="Start date must be on or before the expiration date",
        )

    return {
        "title": title,
        "message": message,
        "start_date": (
            announcement.start_date.isoformat()
            if announcement.start_date
            else None
        ),
        "expiration_date": announcement.expiration_date.isoformat(),
    }


@router.get("", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Return announcements currently active for public display."""
    today = datetime.now(timezone.utc).date().isoformat()
    query = {
        "expiration_date": {"$gte": today},
        "$or": [
            {"start_date": None},
            {"start_date": {"$lte": today}},
            {"start_date": {"$exists": False}},
        ],
    }
    return [
        _announcement_data(announcement)
        for announcement in announcements_collection.find(query).sort(
            "expiration_date", 1
        )
    ]


@router.get(
    "/manage",
    response_model=List[Dict[str, Any]],
    dependencies=[Depends(get_authenticated_teacher)],
)
def get_all_announcements() -> List[Dict[str, Any]]:
    """List every announcement for signed-in teachers."""
    return [
        _announcement_data(announcement)
        for announcement in announcements_collection.find().sort(
            "expiration_date", 1
        )
    ]


@router.post(
    "",
    response_model=Dict[str, str],
    status_code=201,
    dependencies=[Depends(get_authenticated_teacher)],
)
def create_announcement(
    announcement: AnnouncementInput,
) -> Dict[str, str]:
    """Create an announcement for signed-in teachers."""
    announcement_id = str(uuid4())
    document = {
        "_id": announcement_id,
        **_validated_data(announcement),
        "created_at": datetime.now(timezone.utc),
    }
    announcements_collection.insert_one(document)
    return {"id": announcement_id}


@router.put(
    "/{announcement_id}",
    response_model=Dict[str, str],
    dependencies=[Depends(get_authenticated_teacher)],
)
def update_announcement(
    announcement_id: str,
    announcement: AnnouncementInput,
) -> Dict[str, str]:
    """Update an existing announcement for signed-in teachers."""
    result = announcements_collection.update_one(
        {"_id": announcement_id},
        {
            "$set": {
                **_validated_data(announcement),
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return {"id": announcement_id}


@router.delete(
    "/{announcement_id}",
    response_model=Dict[str, str],
    dependencies=[Depends(get_authenticated_teacher)],
)
def delete_announcement(
    announcement_id: str,
) -> Dict[str, str]:
    """Delete an announcement for signed-in teachers."""
    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return {"message": "Announcement deleted"}
