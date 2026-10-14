from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import GRADES

EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
PHONE = r"^[0-9+\-\s]{7,20}$"
YEAR = r"^\d{4}-\d{2}$"


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class SchoolIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    about: Optional[str] = Field(default=None, max_length=2000)
    mission: Optional[str] = Field(default=None, max_length=1000)
    vision: Optional[str] = Field(default=None, max_length=1000)
    address: Optional[str] = Field(default=None, max_length=300)
    contact: Optional[str] = Field(default=None, max_length=200)
    founded: Optional[str] = Field(default=None, max_length=10)


class NewSchoolIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    owner_name: str = Field(min_length=2, max_length=100)
    owner_username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")


class UserIn(BaseModel):
    # ignored for students: their login name is always their student ID
    username: Optional[str] = Field(default=None, min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    full_name: str = Field(min_length=2, max_length=100)
    role: str = Field(pattern=r"^(admin|staff|student)$")
    permissions: list[str] = []
    student_id: Optional[int] = None
    staff_id: Optional[int] = None


class UserUpdateIn(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    permissions: Optional[list[str]] = None
    active: Optional[bool] = None


class StudentIn(BaseModel):
    admission_no: Optional[str] = Field(default=None, max_length=20)  # ignored: the ID is generated
    name: str = Field(min_length=2, max_length=100)
    gender: str = Field(pattern=r"^(Male|Female|Other)$")
    dob: date
    grade: str
    section: str = Field(pattern=r"^[A-Z]$")
    guardian_name: str = Field(min_length=2, max_length=100)
    phone: str = Field(pattern=PHONE)
    email: Optional[str] = Field(default=None, max_length=120, pattern=EMAIL)
    address: Optional[str] = Field(default=None, max_length=250)
    blood_group: Optional[str] = Field(default=None, pattern=r"^(A|B|AB|O)[+-]$")

    @field_validator("grade")
    @classmethod
    def _grade(cls, v: str) -> str:
        if v not in GRADES:
            raise ValueError("invalid grade")
        return v

    @field_validator("dob")
    @classmethod
    def _dob(cls, v: date) -> date:
        if v >= date.today():
            raise ValueError("dob must be in the past")
        return v


class MarkIn(BaseModel):
    subject_id: int
    exam: str = Field(pattern=r"^(UT1|Midterm|UT2|Final)$")
    academic_year: str = Field(pattern=YEAR)
    score: float = Field(ge=0)


class PaymentIn(BaseModel):
    academic_year: str = Field(pattern=YEAR)
    amount: float = Field(gt=0, le=10_000_000)
    mode: str = Field(pattern=r"^(Cash|UPI|Card|Cheque|Bank Transfer)$")


class FeeIn(BaseModel):
    academic_year: str = Field(pattern=YEAR)
    total_amount: float = Field(ge=0, le=10_000_000)


class StaffIn(BaseModel):
    employee_id: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=2, max_length=100)
    gender: str = Field(pattern=r"^(Male|Female|Other)$")
    designation: str = Field(min_length=2, max_length=80)
    department: str = Field(min_length=2, max_length=80)
    qualification: str = Field(min_length=2, max_length=120)
    experience_years: int = Field(ge=0, le=60)
    subjects: Optional[str] = Field(default=None, max_length=200)
    class_teacher_of: Optional[str] = Field(default=None, max_length=10)
    phone: str = Field(pattern=PHONE)
    email: str = Field(max_length=120, pattern=EMAIL)
    joined_on: date
    bio: Optional[str] = Field(default=None, max_length=1000)


class SubjectIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    grade: str

    @field_validator("grade")
    @classmethod
    def _grade(cls, v: str) -> str:
        if v not in GRADES:
            raise ValueError("invalid grade")
        return v


class SubjectUpdateIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)


class ChapterIn(BaseModel):
    number: int = Field(ge=1, le=200)
    title: str = Field(min_length=2, max_length=150)
    description: Optional[str] = Field(default=None, max_length=1000)


class EventIn(BaseModel):
    title: str = Field(min_length=2, max_length=150)
    description: str = Field(min_length=1, max_length=2000)
    date: date
    location: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=2, max_length=40)


class GalleryIn(BaseModel):
    title: str = Field(min_length=2, max_length=150)
    category: str = Field(min_length=2, max_length=40)
    caption: Optional[str] = Field(default=None, max_length=300)
    taken_on: date


class GoalIn(BaseModel):
    title: str = Field(min_length=2, max_length=150)
    description: str = Field(min_length=1, max_length=2000)
    target_year: int = Field(ge=2000, le=2100)
    progress: int = Field(ge=0, le=100)
    status: str = Field(pattern=r"^(Planned|In Progress|Completed)$")


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=1000)

    @field_validator("body")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message is empty")
        return v
