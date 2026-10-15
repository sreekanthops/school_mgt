"""Forgot-password recovery with three security questions.

Setup (signed in): the user is given 3 random questions from a bank and answers them; answers are normalised and
stored only as bcrypt hashes. Recovery (signed out): the same 3 questions are shown again; all 3 must be right to
choose a new password. Unknown users, users who never set up recovery and real users all get the same-looking
questions and the same generic failure, so the form cannot be used to find out who has an account.

If someone cannot recover this way, an admin/IT person with the 'users.manage' permission (or the platform
superadmin for an owner) issues a temporary password from Users & Access; it is shared in person and the user is
forced to choose their own before doing anything else."""
import hashlib
import hmac
import logging
import random
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import JWT_SECRET
from ..db import get_db
from ..models import School, User
from ..security import (_fails, current_user, hash_password, is_locked, rate_limit, record_failure,
                        verify_password)

router = APIRouter(prefix="/api/auth")
log = logging.getLogger("school.recovery")

QUESTIONS = [
    "What was the name of your first pet, or a pet you loved as a child?",
    "What was the name of the street you lived on as a child?",
    "What is the first name of your childhood best friend?",
    "In which town or village did your mother grow up?",
    "What was the name of the first school you attended?",
    "What is the surname of your favourite teacher?",
    "What was the first film you watched in a cinema?",
    "What is the title of the first book you remember loving?",
    "What is the first name of your paternal grandmother?",
    "What was your favourite game to play as a child?",
    "What was the first dish you learned to cook, or loved eating as a child?",
    "What was the name of your favourite toy or cartoon character as a child?",
]
COUNT = 3
MAX_FORGOT_FAILS = 5
# A real hash of nothing in particular: checked when the account does not exist so timing looks the same.
_DUMMY_HASH = hash_password("not-a-real-answer")
GENERIC_FAIL = ("Those answers did not match, or recovery is not set up for this account. "
                "Please contact the school admin or IT department for a temporary password.")


def norm(answer: str) -> str:
    """Case, spacing and punctuation do not matter: ' The  Rex! ' == 'the rex'."""
    return " ".join(re.sub(r"[^a-z0-9 ]", "", answer.lower()).split())


def _questions_for(username: str, user: Optional[User]) -> list[int]:
    if user and user.recovery_q:
        return [int(x) for x in user.recovery_q.split(",")]
    # decoy: stable per username, so asking twice gives the same questions as for a real account
    seed = int.from_bytes(hmac.new(JWT_SECRET.encode(), f"decoy:{username}".encode(), hashlib.sha256).digest()[:8], "big")
    return random.Random(seed).sample(range(len(QUESTIONS)), COUNT)


def _out(ids: list[int]) -> list[dict]:
    return [{"id": i, "text": QUESTIONS[i]} for i in ids]


class AnswerIn(BaseModel):
    id: int = Field(ge=0, lt=len(QUESTIONS))
    answer: str = Field(min_length=1, max_length=80)


class SetupIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    answers: list[AnswerIn] = Field(min_length=COUNT, max_length=COUNT)


class ForgotQIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)


class ForgotResetIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    answers: list[str] = Field(min_length=COUNT, max_length=COUNT)
    new_password: str = Field(min_length=10, max_length=128)


# ---------- signed in: set up / change the questions ----------
@router.get("/recovery/setup")
def setup_questions(user: User = Depends(current_user)):
    """A fresh random set of questions to answer (a different set each call; the current set is kept until saved)."""
    ids = random.sample(range(len(QUESTIONS)), COUNT)
    return {"configured": bool(user.recovery_hashes), "questions": _out(ids)}


@router.post("/recovery/setup", status_code=204)
def save_setup(data: SetupIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rate_limit(f"recovery-setup:{user.id}", 10)
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    ids = [a.id for a in data.answers]
    if len(set(ids)) != COUNT:
        raise HTTPException(422, "Answer three different questions")
    answers = [norm(a.answer) for a in data.answers]
    if any(len(a) < 3 for a in answers):
        raise HTTPException(422, "Each answer needs at least 3 letters or digits")
    if len(set(answers)) != COUNT:
        raise HTTPException(422, "Use a different answer for each question")
    user.recovery_q = ",".join(str(i) for i in ids)
    user.recovery_hashes = [hash_password(a) for a in answers]
    db.commit()
    log.info("recovery_set", extra={"user_id": user.id})


# ---------- signed out: forgot password ----------
def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/forgot/questions")
def forgot_questions(data: ForgotQIn, request: Request, db: Session = Depends(get_db)):
    rate_limit(f"forgot-q:{_ip(request)}", 30)
    user = db.scalar(select(User).where(User.username == data.username.strip()))
    return {"questions": _out(_questions_for(data.username.strip(), user))}


@router.post("/forgot/reset", status_code=204)
def forgot_reset(data: ForgotResetIn, request: Request, db: Session = Depends(get_db)):
    name = data.username.strip()
    rate_limit(f"forgot-r:{_ip(request)}", 30)
    key = f"forgot:{name}"
    if is_locked(key, MAX_FORGOT_FAILS):
        raise HTTPException(429, "Too many failed attempts. Try again later, or contact the school admin or IT department.")
    user = db.scalar(select(User).where(User.username == name))
    ready = bool(user and user.active and user.recovery_hashes and user.recovery_q)
    if ready and user.school_id:
        school = db.get(School, user.school_id)
        ready = bool(school and school.active)
    hashes = user.recovery_hashes if ready else [_DUMMY_HASH] * COUNT
    # check all three every time so a wrong first answer takes as long as a wrong last one
    results = [verify_password(norm(a), h) for a, h in zip(data.answers, hashes)]
    if not (ready and all(results)):
        record_failure(key)
        raise HTTPException(400, GENERIC_FAIL)
    user.password_hash = hash_password(data.new_password)
    user.must_change = False
    db.commit()
    _fails.pop(key, None)
    _fails.pop(name, None)  # also lifts a sign-in lockout caused by the forgotten password
    log.info("password_reset_via_questions", extra={"user_id": user.id})
