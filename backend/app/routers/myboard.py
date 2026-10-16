"""Personal sticky notes — private per-user notes on My Board.

Each user can create, edit and delete their own notes. Notes are never shared.
All authenticated school users can use this (admin, staff, student).
"""
import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import PersonalNote, _utcnow
from ..security import school_user
from ..models import User

router = APIRouter(prefix="/api/myboard")

# Allowed note colours (sticky note palette)
NOTE_COLORS = {"#fef08a", "#bbf7d0", "#bfdbfe", "#fed7aa", "#f5d0fe", "#fecaca",
               "#e0f2fe", "#d1fae5", "#fef3c7", "#f3e8ff", "#ffffff", "#1f2328"}
TEXT_COLORS = {"#1f2328", "#ffffff", "#5b4bdb", "#16a34a", "#e11d48", "#d97706",
               "#0284c7", "#9333ea", "#374151"}

MAX_NOTES = 50   # per user


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    note_color: str = Field(default="#fef08a", max_length=12)
    text_color: str = Field(default="#1f2328", max_length=12)
    bold: bool = False
    italic: bool = False


def _out(n: PersonalNote) -> dict:
    return {
        "id": n.id,
        "text": n.text,
        "note_color": n.note_color,
        "text_color": n.text_color,
        "bold": n.bold,
        "italic": n.italic,
        "created_at": n.created_at.isoformat() + "Z",
        "updated_at": (n.updated_at.isoformat() + "Z") if n.updated_at else None,
    }


def _validate_colors(data: NoteIn) -> None:
    if data.note_color not in NOTE_COLORS:
        raise HTTPException(422, f"Invalid note colour. Choose from: {', '.join(sorted(NOTE_COLORS))}")
    if data.text_color not in TEXT_COLORS:
        raise HTTPException(422, f"Invalid text colour. Choose from: {', '.join(sorted(TEXT_COLORS))}")


@router.get("/notes")
def list_notes(user: User = Depends(school_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(PersonalNote)
        .where(PersonalNote.user_id == user.id)
        .order_by(PersonalNote.created_at.desc())
    ).all()
    return [_out(n) for n in rows]


@router.post("/notes", status_code=201)
def create_note(data: NoteIn, user: User = Depends(school_user), db: Session = Depends(get_db)):
    _validate_colors(data)
    from sqlalchemy import func as _func
    n_existing = db.scalar(
        select(_func.count()).select_from(PersonalNote)
        .where(PersonalNote.user_id == user.id)
    ) or 0
    if n_existing >= MAX_NOTES:
        raise HTTPException(400, f"You can have at most {MAX_NOTES} notes. Delete some first.")
    note = PersonalNote(
        user_id=user.id,
        school_id=user.school_id,
        text=data.text,
        note_color=data.note_color,
        text_color=data.text_color,
        bold=data.bold,
        italic=data.italic,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return _out(note)


@router.put("/notes/{nid}")
def update_note(nid: int, data: NoteIn, user: User = Depends(school_user), db: Session = Depends(get_db)):
    _validate_colors(data)
    note = db.scalar(
        select(PersonalNote).where(PersonalNote.id == nid, PersonalNote.user_id == user.id)
    )
    if not note:
        raise HTTPException(404, "Note not found")
    note.text = data.text
    note.note_color = data.note_color
    note.text_color = data.text_color
    note.bold = data.bold
    note.italic = data.italic
    note.updated_at = _utcnow()
    db.commit()
    return _out(note)


@router.delete("/notes/{nid}", status_code=204)
def delete_note(nid: int, user: User = Depends(school_user), db: Session = Depends(get_db)):
    note = db.scalar(
        select(PersonalNote).where(PersonalNote.id == nid, PersonalNote.user_id == user.id)
    )
    if not note:
        raise HTTPException(404, "Note not found")
    db.delete(note)
    db.commit()
