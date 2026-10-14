"""Direct messages between people in the same school.

Rules: every query is scoped to the caller's school. Students may write to staff and admins only
(never to other students). Staff and admins may write to anyone in the school. Messages persist until
a person clears the conversation, which hides it from their own view only.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from .. import storage
from ..db import get_db
from ..models import DirectMessage, Staff, Student, User
from ..schemas import MessageIn
from ..security import school_user

router = APIRouter(prefix="/api/messages")
PAGE = 200


def _contact(db: Session, u: User) -> dict:
    out = {"id": u.id, "name": u.full_name, "role": u.role, "subtitle": u.role.capitalize(),
           "photo": None}
    if u.staff_id and (s := db.get(Staff, u.staff_id)):
        out["subtitle"] = s.designation
        out["photo"] = {"kind": "staff", "id": s.id, "has": bool(s.photo), "v": storage.version(s.photo)}
    elif u.student_id and (st := db.get(Student, u.student_id)):
        out["subtitle"] = f"Student · Class {st.grade}-{st.section}"
        out["photo"] = {"kind": "students", "id": st.id, "has": bool(st.photo), "v": storage.version(st.photo)}
    elif u.role == "admin":
        out["subtitle"] = "School owner"
    return out


def _allowed(me: User, other: User) -> bool:
    if other.id == me.id or not other.active or other.school_id != me.school_id or other.role == "superadmin":
        return False
    if me.role == "student" and other.role == "student":
        return False
    return True


def _peer(db: Session, me: User, uid: int) -> User:
    other = db.get(User, uid)
    if not other or not _allowed(me, other):
        raise HTTPException(404, "Not found")  # same response whether missing, other school or not allowed
    return other


def _visible(me: User, other_id: int):
    """Messages between me and other that I have not cleared."""
    return or_(
        and_(DirectMessage.sender_id == me.id, DirectMessage.recipient_id == other_id, DirectMessage.hidden_sender.is_(False)),
        and_(DirectMessage.sender_id == other_id, DirectMessage.recipient_id == me.id, DirectMessage.hidden_recipient.is_(False)),
    )


def _out(m: DirectMessage, me: User) -> dict:
    return {"id": m.id, "mine": m.sender_id == me.id, "body": m.body, "at": m.created_at.isoformat() + "Z"}


@router.get("/contacts")
def contacts(me: User = Depends(school_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(User).where(User.school_id == me.school_id, User.active.is_(True), User.id != me.id,
                                         User.role != "superadmin").order_by(User.full_name)).all()
    return [_contact(db, u) for u in rows if _allowed(me, u)]


@router.get("/threads")
def threads(me: User = Depends(school_user), db: Session = Depends(get_db)):
    """One row per person I have exchanged (uncleared) messages with, newest first."""
    mine = db.scalars(select(DirectMessage).where(or_(
        and_(DirectMessage.sender_id == me.id, DirectMessage.hidden_sender.is_(False)),
        and_(DirectMessage.recipient_id == me.id, DirectMessage.hidden_recipient.is_(False)),
    )).order_by(DirectMessage.id.desc())).all()
    seen: dict[int, dict] = {}
    for m in mine:
        other_id = m.recipient_id if m.sender_id == me.id else m.sender_id
        t = seen.setdefault(other_id, {"last": m, "unread": 0})
        if m.recipient_id == me.id and not m.read:
            t["unread"] += 1
    out = []
    for other_id, t in seen.items():
        other = db.get(User, other_id)
        if not other or not _allowed(me, other):
            continue
        out.append({**_contact(db, other), "last": t["last"].body[:80], "last_at": t["last"].created_at.isoformat() + "Z",
                    "last_mine": t["last"].sender_id == me.id, "unread": t["unread"]})
    return out


@router.get("/unread")
def unread(me: User = Depends(school_user), db: Session = Depends(get_db)):
    n = db.scalar(select(func.count()).select_from(DirectMessage).where(
        DirectMessage.recipient_id == me.id, DirectMessage.read.is_(False), DirectMessage.hidden_recipient.is_(False)))
    return {"count": n}


@router.get("/with/{uid}")
def conversation(uid: int, me: User = Depends(school_user), db: Session = Depends(get_db)):
    other = _peer(db, me, uid)
    rows = db.scalars(select(DirectMessage).where(_visible(me, uid)).order_by(DirectMessage.id.desc()).limit(PAGE)).all()[::-1]
    db.execute(update(DirectMessage).where(DirectMessage.sender_id == uid, DirectMessage.recipient_id == me.id,
                                           DirectMessage.read.is_(False)).values(read=True))
    db.commit()
    return {"with": _contact(db, other), "messages": [_out(m, me) for m in rows]}


@router.post("/with/{uid}", status_code=201)
def send(uid: int, data: MessageIn, me: User = Depends(school_user), db: Session = Depends(get_db)):
    other = _peer(db, me, uid)
    m = DirectMessage(school_id=me.school_id, sender_id=me.id, recipient_id=other.id, body=data.body)
    db.add(m)
    db.commit()
    return _out(m, me)


@router.delete("/with/{uid}", status_code=204)
def clear(uid: int, me: User = Depends(school_user), db: Session = Depends(get_db)):
    """Clears the conversation from my side only; the other person keeps their copy."""
    _peer(db, me, uid)
    db.execute(update(DirectMessage).where(DirectMessage.sender_id == me.id, DirectMessage.recipient_id == uid)
               .values(hidden_sender=True))
    db.execute(update(DirectMessage).where(DirectMessage.sender_id == uid, DirectMessage.recipient_id == me.id)
               .values(hidden_recipient=True))
    db.commit()
