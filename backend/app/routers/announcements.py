"""School-wide notices from the owner (or anyone granted announcements.manage) to staff and students."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_owned
from ..models import GRADES, Announcement, AnnouncementRead, Student, User
from ..security import need, perm_set, rate_limit, school_user

router = APIRouter(prefix="/api")
AUDIENCES = ("all", "staff", "students", "class")


class AnnouncementIn(BaseModel):
    title: str = Field(min_length=2, max_length=150)
    body: str = Field(min_length=1, max_length=2000)
    audience: str = "all"
    grade: Optional[str] = None
    pinned: bool = False

    @field_validator("title", "body")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be empty")
        return v

    @model_validator(mode="after")
    def _check(self):
        if self.audience not in AUDIENCES:
            raise ValueError("invalid audience")
        if self.audience == "class":
            if self.grade not in GRADES:
                raise ValueError("choose a class")
        else:
            self.grade = None
        return self


def _my_grade(db: Session, user: User) -> Optional[str]:
    if user.role != "student" or not user.student_id:
        return None
    s = db.get(Student, user.student_id)
    return s.grade if s else None


def _visible(db: Session, user: User):
    """Query filter: what this person is allowed to read. Staff-side users see everything their school posted."""
    stmt = select(Announcement).where(Announcement.school_id == user.school_id)
    if user.role == "student":
        g = _my_grade(db, user)
        stmt = stmt.where((Announcement.audience.in_(("all", "students")))
                          | ((Announcement.audience == "class") & (Announcement.grade == g)))
    return stmt


def _out(a: Announcement, read: bool, can_manage: bool) -> dict:
    return {"id": a.id, "title": a.title, "body": a.body, "audience": a.audience, "grade": a.grade, "pinned": a.pinned,
            "author": a.author_name, "at": a.created_at.isoformat() + "Z", "read": read, "can_delete": can_manage}


@router.get("/announcements")
def list_announcements(user: User = Depends(school_user), db: Session = Depends(get_db)):
    rows = db.scalars(_visible(db, user).order_by(Announcement.pinned.desc(), Announcement.id.desc()).limit(100)).all()
    seen = set(db.scalars(select(AnnouncementRead.announcement_id).where(
        AnnouncementRead.user_id == user.id, AnnouncementRead.announcement_id.in_([a.id for a in rows] or [0]))))
    can = "announcements.manage" in perm_set(user)
    return [_out(a, a.id in seen, can) for a in rows]


@router.get("/announcements/unread")
def unread(user: User = Depends(school_user), db: Session = Depends(get_db)):
    ids = _visible(db, user).with_only_columns(Announcement.id).subquery()
    total = db.scalar(select(func.count()).select_from(ids))
    seen = db.scalar(select(func.count()).select_from(AnnouncementRead).where(
        AnnouncementRead.user_id == user.id, AnnouncementRead.announcement_id.in_(select(ids))))
    return {"count": total - seen}


@router.post("/announcements/read-all", status_code=204)
def read_all(user: User = Depends(school_user), db: Session = Depends(get_db)):
    seen = set(db.scalars(select(AnnouncementRead.announcement_id).where(AnnouncementRead.user_id == user.id)))
    for aid in db.scalars(_visible(db, user).with_only_columns(Announcement.id)):
        if aid not in seen:
            db.add(AnnouncementRead(announcement_id=aid, user_id=user.id))
    try:
        db.commit()
    except IntegrityError:  # two tabs marking at once; the first one won
        db.rollback()


@router.post("/announcements", status_code=201)
def post_announcement(data: AnnouncementIn, user: User = Depends(need("announcements.manage")),
                      db: Session = Depends(get_db)):
    rate_limit(f"announce:{user.id}", 30)
    a = Announcement(school_id=user.school_id, author_name=user.full_name, **data.model_dump())
    db.add(a)
    db.flush()
    db.add(AnnouncementRead(announcement_id=a.id, user_id=user.id))  # your own post is not "new" to you
    db.commit()
    return _out(a, True, True)


@router.put("/announcements/{aid}/pin")
def pin(aid: int, pinned: bool = Query(...), user: User = Depends(need("announcements.manage")),
        db: Session = Depends(get_db)):
    a = get_owned(db, Announcement, aid, user.school_id)
    a.pinned = pinned
    db.commit()
    return {"id": a.id, "pinned": a.pinned}


@router.delete("/announcements/{aid}", status_code=204)
def delete_announcement(aid: int, user: User = Depends(need("announcements.manage")), db: Session = Depends(get_db)):
    db.delete(get_owned(db, Announcement, aid, user.school_id))
    db.commit()
