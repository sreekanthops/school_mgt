"""Shared helpers. Every lookup of tenant data goes through these so a record from another
school behaves exactly like a missing record (404)."""
from datetime import date
from typing import Optional, Type

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Chapter, Staff, Student, Subject, User
from .security import perm_set

# Every login ID is  <school id><YYYY><letter><number>  (the letter keeps school id and year unambiguous):
#   s = student  <class 2 digits><roll 3 digits>   12026s09011 = school 1, 2026, class 9, roll 011
#   t = teacher / staff  <3 digits>                12026t007
#   p = principal        <3 digits>                12026p001
#   o = owner (school admin) <3 digits>            12026o001
# LKG/UKG have no class number, so they use 90/91. The ID is also the person's login name and never changes.
CLASS_CODE = {"LKG": "90", "UKG": "91", **{str(i): f"{i:02d}" for i in range(1, 11)}}


def code_prefix(school_id: int, letter: str, grade: Optional[str] = None, year: Optional[int] = None) -> str:
    return f"{school_id}{year or date.today().year}{letter}{CLASS_CODE[grade] if grade else ''}"


def make_code(school_id: int, letter: str, n: int, grade: Optional[str] = None, year: Optional[int] = None) -> str:
    return f"{code_prefix(school_id, letter, grade, year)}{n:03d}"


def next_code(db: Session, school_id: int, letter: str, grade: Optional[str] = None, year: Optional[int] = None) -> str:
    """Next free ID with this prefix. Looks at logins, student IDs and staff IDs, and counts up from the
    highest number in use (numbers run 001-999)."""
    prefix = code_prefix(school_id, letter, grade, year)
    taken = list(db.scalars(select(User.username).where(User.username.like(f"{prefix}%"))))
    taken += db.scalars(select(Student.admission_no).where(Student.admission_no.like(f"{prefix}%")))
    taken += db.scalars(select(Staff.employee_id).where(Staff.employee_id.like(f"{prefix}%")))
    nums = [int(c[len(prefix):]) for c in taken if len(c) == len(prefix) + 3 and c[len(prefix):].isdigit()]
    nxt = max(nums, default=0) + 1
    if nxt > 999:
        raise HTTPException(409, "No numbers left for this ID series")
    return make_code(school_id, letter, nxt, grade, year)


def staff_letter(designation: str) -> str:
    """Principal gets 'p'; every other staff member (including the vice principal) gets 't'."""
    return "p" if designation.strip().lower() == "principal" else "t"


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
