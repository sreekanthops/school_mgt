"""Seed demo data. Run: python -m app.seed [--reset]

Creates: a platform superadmin, a demo school (owner admin, a teacher login, a student login, full
data) and a second EMPTY school to show tenant isolation. Passwords come from *_PASSWORD variables in
.env; any missing one is generated and appended to .env (git-ignored).
"""
import os
import random
import secrets
import sys
from datetime import date, timedelta

from sqlalchemy import select

from .config import CURRENT_YEAR, ENV_PATH
from .db import Base, SessionLocal, engine
from .models import (EXAMS, GRADES, Chapter, Event, Fee, GalleryItem, Goal, Mark, Payment, School, Staff,
                     Student, Subject, User)
from .deps import CLASS_CODE
from .security import TEACHER_DEFAULT, hash_password

random.seed(42)

PRIMARY_EARLY = ["English", "Mathematics", "Rhymes", "Drawing", "Story Time"]
LOWER = ["English", "Hindi", "Telugu", "Mathematics", "EVS", "Computer Basics", "Art & Craft", "Physical Education"]
MIDDLE = ["English", "Hindi", "Telugu", "Mathematics", "Science", "Social Studies", "Computer Science", "Physical Education"]
SECONDARY = ["English", "Hindi", "Telugu", "Mathematics", "Physics", "Chemistry", "Biology", "Social Studies", "Computer Science"]

CHAPTERS = {
    "Mathematics": ["Number Systems", "Fractions and Decimals", "Algebra Basics", "Geometry", "Data Handling"],
    "English": ["Prose: Stories", "Poetry", "Grammar", "Writing Skills", "Reading Comprehension"],
    "Science": ["Matter Around Us", "Living World", "Motion and Force", "Light and Sound", "Our Environment"],
    "Physics": ["Motion", "Force and Laws", "Gravitation", "Work and Energy", "Sound"],
    "Chemistry": ["Matter", "Atoms and Molecules", "Chemical Reactions", "Acids and Bases", "Carbon Compounds"],
    "Biology": ["Cell Structure", "Tissues", "Life Processes", "Heredity", "Environment"],
    "Social Studies": ["History: Early Societies", "Geography: Our Earth", "Civics: Government", "Economics Basics", "Map Skills"],
    "Computer Science": ["Computer Basics", "Internet Safety", "Spreadsheets", "Programming Intro", "Algorithms"],
}


def subjects_for(grade: str) -> list[str]:
    if grade in ("LKG", "UKG"):
        return PRIMARY_EARLY
    n = int(grade)
    return LOWER if n <= 4 else MIDDLE if n <= 7 else SECONDARY


MALE = ["Aarav", "Vihaan", "Arjun", "Rohan", "Kabir", "Ishaan", "Aditya", "Karthik", "Rahul", "Siddharth", "Varun", "Nikhil"]
FEMALE = ["Ananya", "Diya", "Meera", "Sanvi", "Kavya", "Riya", "Aadhya", "Pooja", "Sneha", "Ishita", "Lakshmi", "Nandini"]
LAST = ["Reddy", "Sharma", "Rao", "Patel", "Naidu", "Kumar", "Iyer", "Gupta", "Verma", "Chowdary", "Singh", "Menon"]
FEE_BY_BAND = {"early": 30000, "lower": 40000, "middle": 50000, "secondary": 60000}


def fee_total(grade: str) -> float:
    if grade in ("LKG", "UKG"):
        return FEE_BY_BAND["early"]
    n = int(grade)
    return FEE_BY_BAND["lower" if n <= 4 else "middle" if n <= 7 else "secondary"]


def ensure_env(key: str) -> str:
    if os.environ.get(key):
        return os.environ[key]
    val = secrets.token_urlsafe(12)
    with open(ENV_PATH, "a") as f:
        f.write(f"\n{key}={val}")
    os.environ[key] = val
    print(f"Generated {key} and saved it to backend/.env")
    return val


def fmt_year(s: int) -> str:
    return f"{s}-{str(s + 1)[2:]}"


def prev_grade(g: str) -> str | None:
    i = GRADES.index(g)
    return GRADES[i - 1] if i > 0 else None


def main(reset: bool):
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    if db.scalar(select(School.id).limit(1)):
        print("Data already present. Use --reset to reseed.")
        return

    pw = {k: ensure_env(k) for k in ("SUPERADMIN_PASSWORD", "ADMIN_PASSWORD", "TEACHER_PASSWORD",
                                     "STUDENT_PASSWORD", "OWNER2_PASSWORD")}

    # ---- platform superadmin + empty second school ----
    db.add(User(school_id=None, username="superadmin", password_hash=hash_password(pw["SUPERADMIN_PASSWORD"]),
                role="superadmin", full_name="Platform Superadmin"))
    school2 = School(name="Greenfield Academy")
    db.add(school2)
    db.flush()
    db.add(User(school_id=school2.id, username="owner2", password_hash=hash_password(pw["OWNER2_PASSWORD"]),
                role="admin", full_name="Greenfield Owner"))

    # ---- demo school ----
    school = School(
        name="Sunrise Public School", founded="1998",
        about="Sunrise Public School is a co-educational school from LKG to Class 10, nurturing curious, confident and responsible learners.",
        mission="To deliver joyful, rigorous and inclusive education that prepares every child for the future.",
        vision="A school where technology and teachers together unlock every student's potential.",
        address="12 Education Avenue, Hyderabad, Telangana.", contact="office@school.example | +91 40 0000 0000")
    db.add(school)
    db.flush()
    sid = school.id
    db.add(User(school_id=sid, username="admin", password_hash=hash_password(pw["ADMIN_PASSWORD"]),
                role="admin", full_name="School Owner"))

    subj = {}
    for g in GRADES:
        for n in subjects_for(g):
            s = Subject(school_id=sid, name=n, grade=g)
            db.add(s)
            subj[(g, n)] = s
    db.flush()
    for (g, n), s in subj.items():
        for i, title in enumerate(CHAPTERS.get(n, [f"Unit {k}" for k in range(1, 5)]), 1):
            db.add(Chapter(subject_id=s.id, number=i, title=title,
                           description=f"{n} — chapter {i} for {'class ' + g if g.isdigit() else g}."))

    first = ["Suresh", "Lakshmi", "Ramesh", "Padma", "Anil", "Sunita", "Vikram", "Deepa", "Manoj", "Rekha", "Prakash", "Swathi", "Harish", "Geeta"]
    staff_rows = []
    for i, g in enumerate(GRADES):
        subs = subjects_for(g)
        staff_rows.append(Staff(
            school_id=sid, employee_id=f"EMP{100 + i}", name=f"{first[i % len(first)]} {LAST[(i * 5) % len(LAST)]}",
            gender="Female" if i % 3 else "Male", designation="Class Teacher",
            department="Early Years" if g in ("LKG", "UKG") else "Primary" if int(g) <= 5 else "Secondary",
            qualification="B.Ed, M.A." if i % 2 else "B.Ed, M.Sc.", experience_years=3 + (i * 7) % 18,
            subjects=", ".join(subs[:2]), class_teacher_of=f"{g}-A", phone=f"+91 98{random.randint(10000000, 99999999)}",
            email=f"emp{100 + i}@school.example", joined_on=date(2024 - (i % 9), 6, 10),
            bio=f"Dedicated educator guiding class {g} with a focus on conceptual clarity."))
    specialists = [
        ("Dr. Anitha Rao", "Principal", "Administration", "Ph.D., M.Ed.", 25, "", "Female"),
        ("Mr. Kiran Kumar", "Vice Principal", "Administration", "M.Sc., B.Ed.", 18, "Mathematics, Physics", "Male"),
        ("Ms. Farah Khan", "Senior Teacher", "Secondary", "M.Sc., B.Ed.", 12, "Chemistry, Biology", "Female"),
        ("Mr. Ravi Teja", "Physical Education Teacher", "Sports", "B.P.Ed", 9, "Physical Education", "Male"),
        ("Ms. Sandhya Iyer", "Computer Teacher", "Technology", "MCA, B.Ed.", 7, "Computer Science, Computer Basics", "Female"),
        ("Mr. Venkat Naidu", "Senior Teacher", "Secondary", "M.A., B.Ed.", 14, "Telugu, Hindi", "Male"),
        ("Ms. Julie Thomas", "Senior Teacher", "Secondary", "M.A., B.Ed.", 11, "English, Social Studies", "Female"),
    ]
    for j, (n, d, dep, q, exp, subs, gen) in enumerate(specialists):
        staff_rows.append(Staff(
            school_id=sid, employee_id=f"EMP{200 + j}", name=n, gender=gen, designation=d, department=dep,
            qualification=q, experience_years=exp, subjects=subs or None, class_teacher_of=None,
            phone=f"+91 97{random.randint(10000000, 99999999)}", email=f"emp{200 + j}@school.example",
            joined_on=date(2024 - exp // 2, 6, 1), bio=f"{d} with {exp} years of experience."))
    db.add_all(staff_rows)
    db.flush()
    # teacher login linked to the class teacher of class 5
    t = next(s for s in staff_rows if s.class_teacher_of == "5-A")
    db.add(User(school_id=sid, username="teacher", password_hash=hash_password(pw["TEACHER_PASSWORD"]), role="staff",
                full_name=t.name, permissions=",".join(TEACHER_DEFAULT), staff_id=t.id))

    cur_start = int(CURRENT_YEAR[:4])
    students = []
    for g in GRADES:
        roll = 0
        for sec in ("A", "B"):
            for _ in range(6):
                roll += 1
                adm = f"{date.today().year}{CLASS_CODE[g]}{roll:03d}"  # student ID = login name
                gender = random.choice(["Male", "Female"])
                name = f"{random.choice(MALE if gender == 'Male' else FEMALE)} {random.choice(LAST)}"
                age = 3 if g == "LKG" else 4 if g == "UKG" else 5 + int(g)
                st = Student(
                    school_id=sid, admission_no=adm, name=name, gender=gender,
                    dob=date(cur_start - age, random.randint(1, 12), random.randint(1, 28)),
                    grade=g, section=sec, guardian_name=f"{random.choice(MALE)} {name.split()[1]}",
                    phone=f"+91 9{random.randint(100000000, 999999999)}", email=f"parent{adm}@example.com",
                    address=f"{random.randint(1, 99)}, Main Road, Hyderabad",
                    blood_group=random.choice(["A+", "B+", "O+", "AB+", "O-", "A-"]))
                db.add(st)
                students.append(st)
    db.flush()
    # every student gets a login: username = student ID. Demo only: they share STUDENT_PASSWORD
    # (hashed once; real students get their own one-time password when created in the app).
    student_hash = hash_password(pw["STUDENT_PASSWORD"])
    db.add_all(User(school_id=sid, username=st.admission_no, password_hash=student_hash, role="student",
                    full_name=st.name, student_id=st.id) for st in students)

    for st in students:
        ability = random.gauss(68, 15)
        weak = random.choice(subjects_for(st.grade)) if random.random() < 0.45 else None
        years = [(CURRENT_YEAR, st.grade)]
        pg = prev_grade(st.grade)
        if pg:
            years.append((fmt_year(cur_start - 1), pg))
        for year, g in years:
            for sname in subjects_for(g):
                base = ability + random.gauss(0, 8) - (28 if sname == weak else 0)
                for i, (exam, mx) in enumerate(EXAMS):
                    p = max(18, min(99, base + i * random.uniform(-1, 3)))
                    db.add(Mark(student_id=st.id, subject_id=subj[(g, sname)].id, exam=exam,
                                academic_year=year, score=round(mx * p / 100, 1), max_score=mx))
        total = fee_total(st.grade)
        db.add(Fee(student_id=st.id, academic_year=CURRENT_YEAR, total_amount=total))
        if pg:
            db.add(Fee(student_id=st.id, academic_year=fmt_year(cur_start - 1), total_amount=fee_total(pg)))
            db.add(Payment(student_id=st.id, academic_year=fmt_year(cur_start - 1), amount=fee_total(pg),
                           paid_on=date(cur_start - 1, 8, 15), mode="UPI", receipt_no=f"OLD-{st.id:05d}"))
        paid_frac = random.choice([1, 1, 0.75, 0.5, 0.5, 0.25, 0])
        if paid_frac:
            db.add(Payment(student_id=st.id, academic_year=CURRENT_YEAR, amount=round(total * paid_frac),
                           paid_on=date(cur_start, 7, 10), mode=random.choice(["Cash", "UPI", "Card"]),
                           receipt_no=f"RCPT-{st.id:05d}-1"))

    today = date.today()
    events = [
        ("Annual Day", "Cultural performances, awards and a showcase of student talent.", today + timedelta(days=45), "Main Auditorium", "Cultural"),
        ("Science Exhibition", "Students present working models and experiments.", today + timedelta(days=20), "Science Block", "Academic"),
        ("Parent-Teacher Meeting", "Term progress discussion with parents.", today + timedelta(days=9), "Classrooms", "Meeting"),
        ("Sports Day", "Track and field events and inter-house matches.", today - timedelta(days=60), "School Ground", "Sports"),
        ("Independence Day", "Flag hoisting and cultural programme.", date(cur_start, 8, 15), "School Ground", "Celebration"),
        ("Book Fair", "A week-long fair to encourage reading.", today - timedelta(days=120), "Library", "Academic"),
    ]
    db.add_all(Event(school_id=sid, title=a, description=b, date=c, location=d, category=e) for a, b, c, d, e in events)
    gallery = [
        ("Sports Day Relay", "Sports", "Final relay of the inter-house meet."),
        ("Science Exhibition Models", "Academic", "Class 9 students with their solar model."),
        ("Annual Day Dance", "Cultural", "Primary wing folk dance performance."),
        ("Library Reading Hour", "Campus", "Weekly reading session."),
        ("Independence Day Parade", "Celebration", "March past by Scouts."),
        ("Robotics Club", "Academic", "Students building line-follower robots."),
        ("Art Competition", "Cultural", "Inter-class painting contest."),
        ("Green Campus Drive", "Campus", "Tree plantation by Class 6."),
    ]
    db.add_all(GalleryItem(school_id=sid, title=t_, category=c, caption=cap, taken_on=today - timedelta(days=i * 17))
               for i, (t_, c, cap) in enumerate(gallery))
    goals = [
        ("Smart Classrooms in all grades", "Interactive displays and digital content for every class.", 2027, 45, "In Progress"),
        ("AI-assisted personalised learning", "Weak-area detection with tailored practice for each student.", 2026, 30, "In Progress"),
        ("Robotics & Coding Lab", "Hands-on STEM lab from class 5 onwards.", 2026, 60, "In Progress"),
        ("Solar-powered campus", "Meet 70% of power needs from solar.", 2028, 15, "Planned"),
        ("100% digital parent communication", "Fees, attendance and progress on the parent app.", 2026, 75, "In Progress"),
        ("Inclusive learning centre", "Resource room and trained special educators.", 2029, 5, "Planned"),
    ]
    db.add_all(Goal(school_id=sid, title=a, description=b, target_year=c, progress=d, status=e) for a, b, c, d, e in goals)
    db.commit()
    print(f"Seeded {len(students)} students, {len(staff_rows)} staff in 'Sunrise Public School' + empty 'Greenfield Academy'.")
    demo = next(s for s in students if s.grade == "5" and s.section == "A")
    print(f"Logins: superadmin / admin / teacher / owner2 / any student ID e.g. {demo.admission_no} "
          "(passwords in backend/.env)")


if __name__ == "__main__":
    main("--reset" in sys.argv)
