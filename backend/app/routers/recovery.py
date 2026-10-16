"""Forgot-password recovery — three tiers.

Tier 1 – Security questions (all roles):
  Setup (signed in): the user picks 3 questions from a bank and stores hashed answers.
  Recovery (signed out): same 3 questions are shown; all 3 must match to reset the password.
  Unknown, un-configured and real users all get the same-looking questions and the same generic
  failure so the form cannot be used to enumerate who has an account.

Tier 2 – Admin/IT temporary password (all roles except owner):
  A user with 'users.manage' issues a temp password from Users & Access; it is given in person.
  The user must choose their own password before anything else works.

Tier 3 – Gmail email link (owner/admin role only):
  The owner configures a personal Gmail address in their Account page.
  On the forgot-password form they choose "I am the school owner" and enter that address.
  A one-time time-limited link is sent; clicking it opens a page to set a new password.
  If SMTP is not configured or the owner has not saved a recovery email, they should contact
  the superadmin who can reset the owner's password from the platform console.
"""
import hashlib
import hmac
import logging
import random
import re
import secrets
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import JWT_SECRET, SMTP_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER
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
# Token TTL for owner email reset links (15 minutes).
_TOKEN_TTL = 15 * 60
# In-memory store: token -> (user_id, expires_at).  Cleared on use or expiry.
_owner_tokens: dict[str, tuple[int, float]] = {}

# A real hash of nothing in particular: checked when the account does not exist so timing is the same.
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
    seed = int.from_bytes(
        hmac.new(JWT_SECRET.encode(), f"decoy:{username}".encode(), hashlib.sha256).digest()[:8], "big"
    )
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
    # Each entry carries the question id the user selected plus their answer.
    # This lets the user pick and answer all three questions in a single form
    # without a separate "fetch questions for this username" round-trip that
    # would allow enumeration of which accounts exist.
    answers: list[AnswerIn] = Field(min_length=COUNT, max_length=COUNT)
    new_password: str = Field(min_length=10, max_length=128)


_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}$")


def _validate_email(email: str) -> str:
    """Normalise and basic-validate an email address (no external dependency)."""
    v = email.lower().strip()
    if not _EMAIL_RE.match(v):
        raise HTTPException(422, "Enter a valid email address")
    return v


class RecoveryEmailIn(BaseModel):
    email: str = Field(min_length=5, max_length=120)


class OwnerEmailIn(BaseModel):
    email: str = Field(min_length=5, max_length=120)
    # The frontend sends the base URL so the reset link points back to the right origin.
    base_url: str = Field(min_length=1, max_length=200)


class OwnerConfirmIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
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


# ---------- signed in (owner only): save / read Gmail recovery email ----------
@router.get("/recovery/email")
def get_recovery_email(user: User = Depends(current_user)):
    """Returns whether a recovery email has been configured (not the address itself)."""
    return {"configured": bool(user.recovery_email),
            "smtp_enabled": bool(SMTP_USER and SMTP_PASSWORD)}


@router.put("/recovery/email", status_code=204)
def set_recovery_email(data: RecoveryEmailIn, user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    """Owner stores the Gmail address that will receive password-reset links.  Any authenticated user
    may set this, but only the admin/owner role is shown the UI card for it."""
    rate_limit(f"recovery-email:{user.id}", 10)
    user.recovery_email = _validate_email(data.email)
    db.commit()
    log.info("recovery_email_set", extra={"user_id": user.id})


# ---------- signed out: forgot password (security questions) ----------
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

    if not ready:
        # Evaluate dummy hashes so timing is identical to the real path.
        for _ in data.answers:
            verify_password(norm("dummy"), _DUMMY_HASH)
        record_failure(key)
        raise HTTPException(400, GENERIC_FAIL)

    # Build a map of question_index -> hash from the stored recovery data.
    stored_ids = [int(x) for x in user.recovery_q.split(",")]
    id_to_hash: dict[int, str] = dict(zip(stored_ids, user.recovery_hashes))

    # The user must submit exactly the 3 question IDs they set up (order doesn't matter).
    submitted_ids = [a.id for a in data.answers]
    if sorted(submitted_ids) != sorted(stored_ids):
        # Wrong question selection — treat as wrong answers; timing is kept uniform.
        for a in data.answers:
            verify_password(norm(a.answer), _DUMMY_HASH)
        record_failure(key)
        raise HTTPException(400, GENERIC_FAIL)

    # Verify every answer against its corresponding hash (constant-time for all three).
    results = [verify_password(norm(a.answer), id_to_hash[a.id]) for a in data.answers]
    if not all(results):
        record_failure(key)
        raise HTTPException(400, GENERIC_FAIL)

    user.password_hash = hash_password(data.new_password)
    user.must_change = False
    db.commit()
    _fails.pop(key, None)
    _fails.pop(name, None)  # also lifts a sign-in lockout caused by the forgotten password
    log.info("password_reset_via_questions", extra={"user_id": user.id})


# ---------- signed out: owner Gmail email reset ----------
def _smtp_enabled() -> bool:
    return bool(SMTP_USER and SMTP_PASSWORD)


def _send_reset_email(to: str, reset_url: str) -> None:
    """Send a password-reset link via SMTP (Gmail App Password).  Raises on failure."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Reset your school owner password"
    msg["From"] = SMTP_FROM or SMTP_USER
    msg["To"] = to
    plain = (
        "You asked to reset your school owner password.\n\n"
        f"Open this link within 15 minutes:\n{reset_url}\n\n"
        "If you did not request this, ignore this email — your password has not changed."
    )
    html = (
        "<p>You asked to reset your school owner password.</p>"
        f'<p><a href="{reset_url}">Reset my password</a></p>'
        "<p>This link is valid for <strong>15 minutes</strong>.</p>"
        "<p>If you did not request this, ignore this email — your password has not changed.</p>"
    )
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
        s.ehlo()
        s.starttls()
        s.login(SMTP_USER, SMTP_PASSWORD)
        s.sendmail(SMTP_FROM or SMTP_USER, [to], msg.as_string())


def _purge_expired_tokens() -> None:
    now = time.time()
    expired = [t for t, (_, exp) in _owner_tokens.items() if exp < now]
    for t in expired:
        _owner_tokens.pop(t, None)


@router.post("/forgot/owner-email", status_code=204)
def owner_forgot_email(data: OwnerEmailIn, request: Request, db: Session = Depends(get_db)):
    """Send a password-reset link to the owner's configured Gmail address.
    Always returns 204 — the response never reveals whether the email matched."""
    rate_limit(f"owner-email:{_ip(request)}", 10)
    _purge_expired_tokens()

    if not _smtp_enabled():
        # Silently succeed so the UI can show "check your inbox" regardless;
        # the email simply never arrives if SMTP is not set up.
        log.warning("owner_reset_email_requested_but_smtp_not_configured")
        return

    email = _validate_email(data.email)
    # Look for an active owner whose recovery_email matches.
    user = db.scalar(
        select(User).where(
            User.recovery_email == email,
            User.role == "admin",
            User.active == True,  # noqa: E712
        )
    )
    if user and user.school_id:
        school = db.get(School, user.school_id)
        if not school or not school.active:
            user = None  # school disabled — silently do nothing

    if user:
        token = secrets.token_urlsafe(32)
        _owner_tokens[token] = (user.id, time.time() + _TOKEN_TTL)
        reset_url = f"{data.base_url.rstrip('/')}/reset-owner-password?token={token}"
        try:
            _send_reset_email(email, reset_url)
            log.info("owner_reset_email_sent", extra={"user_id": user.id})
        except Exception as exc:
            # Don't leak SMTP errors to the caller.
            log.error("owner_reset_email_failed", exc_info=exc)
            _owner_tokens.pop(token, None)


@router.post("/forgot/owner-confirm", status_code=204)
def owner_forgot_confirm(data: OwnerConfirmIn, db: Session = Depends(get_db)):
    """Consume a one-time owner reset token and set a new password."""
    _purge_expired_tokens()
    entry = _owner_tokens.get(data.token)
    if not entry or time.time() > entry[1]:
        _owner_tokens.pop(data.token, None)
        raise HTTPException(400, "This link has expired or is invalid. Please request a new one.")
    user_id, _ = entry
    user = db.get(User, user_id)
    if not user or not user.active or user.role != "admin":
        raise HTTPException(400, "This link has expired or is invalid. Please request a new one.")
    user.password_hash = hash_password(data.new_password)
    user.must_change = False
    db.commit()
    _owner_tokens.pop(data.token, None)
    _fails.pop(user.username, None)  # lift any sign-in lockout
    log.info("owner_password_reset_via_email", extra={"user_id": user.id})
