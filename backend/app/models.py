import datetime as dt
from typing import Optional

from sqlalchemy import (JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

GRADES = ["LKG", "UKG"] + [str(i) for i in range(1, 11)]
# (exam name, max score)
EXAMS = [("UT1", 25), ("Midterm", 50), ("UT2", 25), ("Final", 100)]
EXAM_MAX = dict(EXAMS)


def _school_fk() -> Mapped[int]:
    return mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)


class School(Base):
    __tablename__ = "schools"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    about: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mission: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vision: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    contact: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    founded: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.date] = mapped_column(Date, default=dt.date.today)
    # ---- platform-managed details (edited by the superadmin) ----
    city: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    board: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    school_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    plan: Mapped[str] = mapped_column(String(20), default="Standard")
    max_students: Mapped[int] = mapped_column(Integer, default=1000)
    max_staff: Mapped[int] = mapped_column(Integer, default=100)
    subscription_end: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # private to the platform team
    academic_year: Mapped[Optional[str]] = mapped_column(String(9), nullable=True)  # NULL => the app default (CURRENT_ACADEMIC_YEAR)


class Branch(Base):
    __tablename__ = "branches"
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = _school_fk()
    name: Mapped[str] = mapped_column(String(100))
    city: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    principal: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_main: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditLog(Base):
    """Superadmin actions on schools. No foreign key on purpose: the trail survives school deletion."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    school_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    actor: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(40))
    detail: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=lambda: dt.datetime.now(dt.timezone.utc).replace(tzinfo=None))


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    # NULL school_id => platform superadmin
    school_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("schools.id", ondelete="CASCADE"), index=True, nullable=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20))  # superadmin | admin | staff | student
    full_name: Mapped[str] = mapped_column(String(100))
    permissions: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # comma separated (staff only)
    student_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), nullable=True, unique=True)
    staff_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("staff.id", ondelete="SET NULL"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    # password recovery: 3 random question ids assigned at setup, and a bcrypt hash of each answer
    recovery_q: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    recovery_hashes: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # set when an admin/IT person issues a temporary password; the user must choose their own before anything else
    must_change: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # owner-only: Gmail address used to receive a password-reset link when security questions cannot be answered
    recovery_email: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (UniqueConstraint("school_id", "name", "grade"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = _school_fk()
    name: Mapped[str] = mapped_column(String(80))
    grade: Mapped[str] = mapped_column(String(5), index=True)


class Chapter(Base):
    __tablename__ = "chapters"
    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (UniqueConstraint("school_id", "admission_no"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = _school_fk()
    admission_no: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100), index=True)
    gender: Mapped[str] = mapped_column(String(10))
    dob: Mapped[dt.date] = mapped_column(Date)
    grade: Mapped[str] = mapped_column(String(5), index=True)
    section: Mapped[str] = mapped_column(String(2))
    guardian_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20))
    email: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)
    blood_group: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    photo: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    legacy_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)  # the id the school used before (smart import)
    pending_photo: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)


class Mark(Base):
    __tablename__ = "marks"
    __table_args__ = (UniqueConstraint("student_id", "subject_id", "exam", "academic_year"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"))
    exam: Mapped[str] = mapped_column(String(20))
    academic_year: Mapped[str] = mapped_column(String(9), index=True)
    score: Mapped[float] = mapped_column(Float)
    max_score: Mapped[float] = mapped_column(Float)


class Fee(Base):
    __tablename__ = "fees"
    __table_args__ = (UniqueConstraint("student_id", "academic_year"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    academic_year: Mapped[str] = mapped_column(String(9))
    total_amount: Mapped[float] = mapped_column(Float)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    academic_year: Mapped[str] = mapped_column(String(9))
    amount: Mapped[float] = mapped_column(Float)
    paid_on: Mapped[dt.date] = mapped_column(Date)
    mode: Mapped[str] = mapped_column(String(20))
    receipt_no: Mapped[str] = mapped_column(String(40), unique=True)


class Staff(Base):
    __tablename__ = "staff"
    __table_args__ = (UniqueConstraint("school_id", "employee_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = _school_fk()
    employee_id: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100), index=True)
    gender: Mapped[str] = mapped_column(String(10))
    designation: Mapped[str] = mapped_column(String(80))
    department: Mapped[str] = mapped_column(String(80))
    qualification: Mapped[str] = mapped_column(String(120))
    experience_years: Mapped[int] = mapped_column(Integer)
    subjects: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    class_teacher_of: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    phone: Mapped[str] = mapped_column(String(20))
    email: Mapped[str] = mapped_column(String(120))
    joined_on: Mapped[dt.date] = mapped_column(Date)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    photo: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    legacy_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = _school_fk()
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    location: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(40))


class GalleryItem(Base):
    __tablename__ = "gallery"
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = _school_fk()
    title: Mapped[str] = mapped_column(String(150))
    category: Mapped[str] = mapped_column(String(40))
    image: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    caption: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    taken_on: Mapped[dt.date] = mapped_column(Date)


class Goal(Base):
    __tablename__ = "goals"
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = _school_fk()
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    target_year: Mapped[int] = mapped_column(Integer)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="Planned")


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)  # naive UTC; the API appends "Z"


class AssistantMessage(Base):
    """One line of a user's private conversation with the school assistant (kept until they clear it)."""
    __tablename__ = "assistant_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    who: Mapped[str] = mapped_column(String(3))  # me | bot
    text: Mapped[str] = mapped_column(Text)
    extra: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # {"cards": [...], "actions": [...]}
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)


class DirectMessage(Base):
    """Person-to-person message inside one school. Each side can clear their own view independently."""
    __tablename__ = "direct_messages"
    __table_args__ = (Index("ix_dm_recipient_unread", "recipient_id", "read"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = _school_fk()
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    hidden_sender: Mapped[bool] = mapped_column(Boolean, default=False)
    hidden_recipient: Mapped[bool] = mapped_column(Boolean, default=False)


class BoardNote(Base):
    """An anonymous idea/opinion on the school board. There is deliberately no user_id column: the only link to
    the writer is a keyed hash (author_key) that lets them delete their own note and be rate limited."""
    __tablename__ = "board_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = _school_fk()
    text: Mapped[str] = mapped_column(String(300))
    color: Mapped[str] = mapped_column(String(10))
    tilt: Mapped[int] = mapped_column(Integer, default=0)
    author_key: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)


class BoardVote(Base):
    """One agree/disagree vote per student per note (voter_key is a keyed hash, not a user id)."""
    __tablename__ = "board_votes"
    __table_args__ = (UniqueConstraint("note_id", "voter_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("board_notes.id", ondelete="CASCADE"), index=True)
    voter_key: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(String(8))  # agree | disagree


class Announcement(Base):
    """A school-wide notice. audience: all | staff | students | class (class needs `grade`)."""
    __tablename__ = "announcements"
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = _school_fk()
    title: Mapped[str] = mapped_column(String(150))
    body: Mapped[str] = mapped_column(String(2000))
    audience: Mapped[str] = mapped_column(String(10), default="all")
    grade: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    author_name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class AnnouncementRead(Base):
    __tablename__ = "announcement_reads"
    __table_args__ = (UniqueConstraint("announcement_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    announcement_id: Mapped[int] = mapped_column(ForeignKey("announcements.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


DAYS_OF_WEEK = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat")


class ClassPeriod(Base):
    """One scheduled slot on the weekly timetable: grade × section × day × period."""
    __tablename__ = "class_periods"
    __table_args__ = (UniqueConstraint("school_id", "grade", "section", "day_of_week", "period_number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = _school_fk()
    grade: Mapped[str] = mapped_column(String(5), index=True)
    section: Mapped[str] = mapped_column(String(2))
    day_of_week: Mapped[str] = mapped_column(String(3))      # Mon..Sat
    period_number: Mapped[int] = mapped_column(Integer)       # 1-based
    start_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)  # "HH:MM"
    end_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    subject_id: Mapped[Optional[int]] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True)
    staff_id: Mapped[Optional[int]] = mapped_column(ForeignKey("staff.id", ondelete="SET NULL"), nullable=True)
    label: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)  # e.g. "Break", "Assembly"


LEAVE_STATUS = ("pending", "approved", "rejected")
LEAVE_TYPES = ("Casual", "Sick", "Earned", "Maternity", "Paternity", "Unpaid", "Other")


class StaffLeave(Base):
    """A leave application submitted by a staff member or a student."""
    __tablename__ = "staff_leaves"
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = _school_fk()
    # exactly one of staff_id / student_id is set
    staff_id: Mapped[Optional[int]] = mapped_column(ForeignKey("staff.id", ondelete="CASCADE"), nullable=True, index=True)
    student_id: Mapped[Optional[int]] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), nullable=True, index=True)
    # who should review this leave (section-head staff user id for student leaves)
    reviewer_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    from_date: Mapped[dt.date] = mapped_column(Date, index=True)
    to_date: Mapped[dt.date] = mapped_column(Date)
    leave_type: Mapped[str] = mapped_column(String(20))       # Casual | Sick | Earned …
    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | approved | rejected
    reviewed_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    applied_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    reviewed_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)


class TimetableLog(Base):
    """Audit trail for timetable modifications made by teachers (self-edit).
    Owner / admin can view these to track who changed what."""
    __tablename__ = "timetable_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = _school_fk()
    period_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # NULL if period was deleted
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    actor_name: Mapped[str] = mapped_column(String(100))                        # snapshot so it survives user deletion
    grade: Mapped[str] = mapped_column(String(5))
    section: Mapped[str] = mapped_column(String(2))
    day_of_week: Mapped[str] = mapped_column(String(3))
    period_number: Mapped[int] = mapped_column(Integer)
    old_subject: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    new_subject: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    old_staff: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    new_staff: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    changed_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class Holiday(Base):
    """A school holiday / non-working day. Visible to all school members."""
    __tablename__ = "holidays"
    __table_args__ = (UniqueConstraint("school_id", "date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = _school_fk()
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    name: Mapped[str] = mapped_column(String(120))            # "Diwali", "Independence Day" …
    description: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    # "national" | "regional" | "school" — for display colour coding
    category: Mapped[str] = mapped_column(String(20), default="school")


ATTENDANCE_STATUS = ("P", "A", "L")  # present | absent | late


class Attendance(Base):
    """One row per student per day."""
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("student_id", "day"), Index("ix_att_school_day", "school_id", "day"))
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = _school_fk()
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    day: Mapped[dt.date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(1))
    marked_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # login ID of whoever marked it


class Invoice(Base):
    """Subscription invoice raised by the platform team. No foreign key on purpose: like the audit trail,
    billing records survive deletion of the school (school_name is a snapshot)."""
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True)
    school_id: Mapped[int] = mapped_column(Integer, index=True)
    school_name: Mapped[str] = mapped_column(String(120))
    plan: Mapped[str] = mapped_column(String(20))
    period_start: Mapped[dt.date] = mapped_column(Date)
    period_end: Mapped[dt.date] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Float)  # before tax
    tax: Mapped[float] = mapped_column(Float)
    total: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(10), default="Pending")  # Pending | Paid | Cancelled
    issued_on: Mapped[dt.date] = mapped_column(Date, default=dt.date.today)
    due_on: Mapped[dt.date] = mapped_column(Date)
    paid_on: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    reference: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)


class ImportJob(Base):
    """An uploaded file waiting to be reviewed (smart import). Holds the school's raw file only until the import
    is confirmed or cancelled, or for 24 hours at most."""
    __tablename__ = "import_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = _school_fk()
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(120))
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class ImportBatch(Base):
    """What a confirmed smart import created, so it can be undone. `created` maps a table name to the ids added."""
    __tablename__ = "import_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = _school_fk()
    user_name: Mapped[str] = mapped_column(String(50))
    filename: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    summary: Mapped[dict] = mapped_column(JSON)
    created: Mapped[dict] = mapped_column(JSON)
    undone: Mapped[bool] = mapped_column(Boolean, default=False)
