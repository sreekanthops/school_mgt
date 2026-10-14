import datetime as dt
from datetime import date
from typing import Optional

from sqlalchemy import Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

GRADES = ["LKG", "UKG"] + [str(i) for i in range(1, 11)]
# (exam name, max score)
EXAMS = [("UT1", 25), ("Midterm", 50), ("UT2", 25), ("Final", 100)]
EXAM_MAX = dict(EXAMS)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20))  # admin | teacher
    full_name: Mapped[str] = mapped_column(String(100))


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (UniqueConstraint("name", "grade"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    grade: Mapped[str] = mapped_column(String(5), index=True)


class Student(Base):
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(primary_key=True)
    admission_no: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    gender: Mapped[str] = mapped_column(String(10))
    dob: Mapped[date] = mapped_column(Date)
    grade: Mapped[str] = mapped_column(String(5), index=True)
    section: Mapped[str] = mapped_column(String(2))
    guardian_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20))
    email: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(250), nullable=True)
    blood_group: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)


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
    paid_on: Mapped[date] = mapped_column(Date)
    mode: Mapped[str] = mapped_column(String(20))
    receipt_no: Mapped[str] = mapped_column(String(30), unique=True)


class Staff(Base):
    __tablename__ = "staff"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[str] = mapped_column(String(20), unique=True)
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
    joined_on: Mapped[date] = mapped_column(Date)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    location: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(40))


class GalleryItem(Base):
    __tablename__ = "gallery"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(150))
    category: Mapped[str] = mapped_column(String(40))
    image_url: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    caption: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    taken_on: Mapped[date] = mapped_column(Date)


class Goal(Base):
    __tablename__ = "goals"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    target_year: Mapped[int] = mapped_column(Integer)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="Planned")


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
