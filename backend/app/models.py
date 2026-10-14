import datetime as dt
from typing import Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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
