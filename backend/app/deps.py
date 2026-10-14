"""Shared helpers. Every lookup of tenant data goes through these so a record from another
school behaves exactly like a missing record (404)."""
from typing import Optional, Type

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import Chapter, Staff, Student, Subject, User
from .security import perm_set


def get_owned(db: Session, model: Type, obj_id: int, school_id: int):
    obj = db.get(model, obj_id)
    if not obj or getattr(obj, "school_id", None) != school_id:
        raise HTTPException(404, "Not found")
    return obj


def get_student(db: Session, user: User, sid: int) -> Student:
    return get_owned(db, Student, sid, user.school_id)


def get_chapter(db: Session, user: User, cid: int) -> tuple[Chapter, Subject]:
    ch = db.get(Chapter, cid)
    subj = db.get(Subject, ch.subject_id) if ch else None
    if not ch or not subj or subj.school_id != user.school_id:
        raise HTTPException(404, "Not found")
    return ch, subj


def can_see_student(user: User, student_id: int) -> bool:
    """Staff with students.view see everyone in their school; a student sees only themself."""
    if "students.view" in perm_set(user):
        return True
    return user.role == "student" and user.student_id == student_id


def can_see_fees(user: User, student_id: int) -> bool:
    p = perm_set(user)
    if "fees.view" in p or "fees.manage" in p:
        return True
    return user.role == "student" and user.student_id == student_id


def photo_url(kind: str, obj_id: int, rel: Optional[str]) -> Optional[str]:
    if not rel:
        return None
    return f"/{kind}/{obj_id}/photo?v={rel.split('/')[-1][:8]}"
