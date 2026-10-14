from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import GRADES

Section = Field(pattern=r"^[A-Z]$")


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class StudentIn(BaseModel):
    admission_no: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=2, max_length=100)
    gender: str = Field(pattern=r"^(Male|Female|Other)$")
    dob: date
    grade: str
    section: str = Section
    guardian_name: str = Field(min_length=2, max_length=100)
    phone: str = Field(pattern=r"^[0-9+\-\s]{7,20}$")
    email: Optional[str] = Field(default=None, max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
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


class StudentOut(StudentIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class MarkIn(BaseModel):
    subject_id: int
    exam: str = Field(pattern=r"^(UT1|Midterm|UT2|Final)$")
    academic_year: str = Field(pattern=r"^\d{4}-\d{2}$")
    score: float = Field(ge=0)


class PaymentIn(BaseModel):
    academic_year: str = Field(pattern=r"^\d{4}-\d{2}$")
    amount: float = Field(gt=0, le=10_000_000)
    mode: str = Field(pattern=r"^(Cash|UPI|Card|Cheque|Bank Transfer)$")


class FeeIn(BaseModel):
    academic_year: str = Field(pattern=r"^\d{4}-\d{2}$")
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
    phone: str = Field(pattern=r"^[0-9+\-\s]{7,20}$")
    email: str = Field(max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    joined_on: date
    bio: Optional[str] = Field(default=None, max_length=1000)


class StaffOut(StaffIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)
