"""Anonymous idea board. Anyone in a school can post a short note; only students vote (one agree/disagree each).

Anonymity: notes and votes store a keyed hash (see security.anon_key), never a user id, and no endpoint returns
who wrote or voted for anything. School moderators (content.manage) can delete any note; authors can delete theirs."""
import random
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import BoardNote, BoardVote, Student, User
from ..moderation import REASON, problem
from ..security import anon_key, perm_set, rate_limit, school_user

router = APIRouter(prefix="/api/board")

COLORS = ["yellow", "pink", "blue", "green", "orange", "lilac"]
MAX_NOTES_SHOWN = 100
POSTS_PER_15_MIN = 5


class NoteIn(BaseModel):
    text: str = Field(min_length=3, max_length=300)

    @field_validator("text")
    @classmethod
    def _clean(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 3:
            raise ValueError("Write at least a few words")
        return v


class CheckIn(BaseModel):
    text: str = Field(default="", max_length=300)


class VoteIn(BaseModel):
    value: str = Field(pattern=r"^(agree|disagree)$")


def _key(user: User) -> str:
    return anon_key("board", user.school_id, user.id)


def _pct(part: int, whole: int) -> float:
    return round(part * 100 / whole, 1) if whole else 0.0


def _note_out(n: BoardNote, tally: dict, mine_vote: Optional[str], me_key: str, can_mod: bool, students: int) -> dict:
    agree, disagree = tally.get("agree", 0), tally.get("disagree", 0)
    total = agree + disagree
    return {
        "id": n.id, "text": n.text, "color": n.color, "tilt": n.tilt, "created_at": n.created_at.isoformat() + "Z",
        "agree": agree, "disagree": disagree, "votes": total,
        "agree_pct": _pct(agree, total), "disagree_pct": _pct(disagree, total) if total else 0.0,
        "participation_pct": _pct(total, students),
        "my_vote": mine_vote, "mine": n.author_key == me_key,
        "can_delete": can_mod or n.author_key == me_key,
    }


@router.get("")
def list_notes(sort: str = Query("new", pattern=r"^(new|top|debated)$"), user: User = Depends(school_user),
               db: Session = Depends(get_db)):
    notes = db.scalars(select(BoardNote).where(BoardNote.school_id == user.school_id)
                       .order_by(BoardNote.id.desc()).limit(MAX_NOTES_SHOWN)).all()
    ids = [n.id for n in notes]
    tallies: dict[int, dict] = {i: {} for i in ids}
    if ids:
        for nid, value, c in db.execute(select(BoardVote.note_id, BoardVote.value, func.count())
                                        .where(BoardVote.note_id.in_(ids)).group_by(BoardVote.note_id, BoardVote.value)):
            tallies[nid][value] = c
    key = _key(user)
    mine = {}
    if user.role == "student" and ids:
        mine = dict(db.execute(select(BoardVote.note_id, BoardVote.value)
                               .where(BoardVote.note_id.in_(ids), BoardVote.voter_key == key)).all())
    students = db.scalar(select(func.count()).select_from(Student).where(Student.school_id == user.school_id)) or 0
    can_mod = "content.manage" in perm_set(user)
    out = [_note_out(n, tallies[n.id], mine.get(n.id), key, can_mod, students) for n in notes]
    if sort == "top":
        out.sort(key=lambda x: (x["agree"] - x["disagree"], x["votes"]), reverse=True)
    elif sort == "debated":
        out.sort(key=lambda x: (min(x["agree"], x["disagree"]), x["votes"]), reverse=True)
    return {"items": out, "can_vote": user.role == "student", "can_moderate": can_mod, "students": students}


@router.post("/check")
def check(data: CheckIn, user: User = Depends(school_user)):
    """Live preview for the editor. Rate limited so it cannot be used to probe the word list."""
    rate_limit(f"board-check:{user.id}", 120)
    return {"ok": problem(data.text) is None}


@router.post("", status_code=201)
def post_note(data: NoteIn, user: User = Depends(school_user), db: Session = Depends(get_db)):
    key = _key(user)
    rate_limit(f"board-post:{key}", POSTS_PER_15_MIN)
    if problem(data.text):
        raise HTTPException(422, REASON)
    n = BoardNote(school_id=user.school_id, text=data.text, color=random.choice(COLORS),
                  tilt=random.randint(-3, 3), author_key=key)
    db.add(n)
    db.commit()
    students = db.scalar(select(func.count()).select_from(Student).where(Student.school_id == user.school_id)) or 0
    return _note_out(n, {}, None, key, "content.manage" in perm_set(user), students)


def _note(db: Session, user: User, nid: int) -> BoardNote:
    n = db.get(BoardNote, nid)
    if not n or n.school_id != user.school_id:
        raise HTTPException(404, "Not found")
    return n


@router.post("/{nid}/vote")
def vote(nid: int, data: VoteIn, user: User = Depends(school_user), db: Session = Depends(get_db)):
    """Students only. One vote per student per note; voting again changes that vote."""
    if user.role != "student":
        raise HTTPException(403, "Only students can vote")
    n = _note(db, user, nid)
    key = _key(user)
    if n.author_key == key:
        raise HTTPException(403, "You cannot vote on your own note")
    row = db.scalar(select(BoardVote).where(BoardVote.note_id == nid, BoardVote.voter_key == key))
    if row:
        row.value = data.value
    else:
        db.add(BoardVote(note_id=nid, voter_key=key, value=data.value))
    db.commit()
    return _note_summary(db, user, n)


@router.delete("/{nid}/vote", status_code=204)
def unvote(nid: int, user: User = Depends(school_user), db: Session = Depends(get_db)):
    n = _note(db, user, nid)
    row = db.scalar(select(BoardVote).where(BoardVote.note_id == n.id, BoardVote.voter_key == _key(user)))
    if row:
        db.delete(row)
        db.commit()


def _note_summary(db: Session, user: User, n: BoardNote) -> dict:
    tally = dict(db.execute(select(BoardVote.value, func.count()).where(BoardVote.note_id == n.id)
                            .group_by(BoardVote.value)).all())
    key = _key(user)
    mine = db.scalar(select(BoardVote.value).where(BoardVote.note_id == n.id, BoardVote.voter_key == key))
    students = db.scalar(select(func.count()).select_from(Student).where(Student.school_id == user.school_id)) or 0
    return _note_out(n, tally, mine, key, "content.manage" in perm_set(user), students)


@router.delete("/{nid}", status_code=204)
def delete_note(nid: int, user: User = Depends(school_user), db: Session = Depends(get_db)):
    n = _note(db, user, nid)
    if n.author_key != _key(user) and "content.manage" not in perm_set(user):
        raise HTTPException(403, "You can only delete your own notes")
    db.delete(n)
    db.commit()
