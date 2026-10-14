"""Subjects & chapters, events, gallery, goals, chatbot. All reads are open to anyone in the school;
all writes need the matching permission."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import chatbot, storage
from ..db import get_db
from ..deps import get_chapter, get_owned
from ..models import GRADES, Chapter, Event, GalleryItem, Goal, Staff, Subject, User
from ..schemas import (ChapterIn, ChatIn, EventIn, GalleryIn, GoalIn, SubjectIn, SubjectUpdateIn)
from ..security import need, perm_set, school_user

router = APIRouter(prefix="/api")


def _can(user: User, perm: str) -> bool:
    return perm in perm_set(user)


# ---------- subjects ----------
@router.get("/subjects")
def list_subjects(user: User = Depends(school_user), db: Session = Depends(get_db)):
    subs = db.scalars(select(Subject).where(Subject.school_id == user.school_id).order_by(Subject.name)).all()
    counts: dict[int, int] = {}
    for (sid,) in db.execute(select(Chapter.subject_id).join(Subject, Subject.id == Chapter.subject_id)
                             .where(Subject.school_id == user.school_id)):
        counts[sid] = counts.get(sid, 0) + 1
    teachers = db.scalars(select(Staff).where(Staff.school_id == user.school_id)).all()
    grouped = {g: [] for g in GRADES}
    for s in subs:
        t = [x.name for x in teachers if x.subjects and s.name in [p.strip() for p in x.subjects.split(",")]]
        grouped[s.grade].append({"id": s.id, "name": s.name, "teachers": t[:3], "chapters": counts.get(s.id, 0)})
    return {"grades": [{"grade": g, "subjects": grouped[g]} for g in GRADES], "can_manage": _can(user, "subjects.manage")}


@router.post("/subjects", status_code=201)
def add_subject(data: SubjectIn, user: User = Depends(need("subjects.manage")), db: Session = Depends(get_db)):
    s = Subject(school_id=user.school_id, name=data.name.strip(), grade=data.grade)
    db.add(s)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "That subject already exists for this class")
    return {"id": s.id, "name": s.name, "grade": s.grade}


@router.put("/subjects/{sid}")
def update_subject(sid: int, data: SubjectUpdateIn, user: User = Depends(need("subjects.manage")),
                   db: Session = Depends(get_db)):
    s = get_owned(db, Subject, sid, user.school_id)
    s.name = data.name.strip()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "That subject already exists for this class")
    return {"id": s.id, "name": s.name, "grade": s.grade}


@router.delete("/subjects/{sid}", status_code=204)
def delete_subject(sid: int, user: User = Depends(need("subjects.manage")), db: Session = Depends(get_db)):
    db.delete(get_owned(db, Subject, sid, user.school_id))
    db.commit()


@router.get("/subjects/{sid}")
def subject_detail(sid: int, user: User = Depends(school_user), db: Session = Depends(get_db)):
    s = get_owned(db, Subject, sid, user.school_id)
    chs = db.scalars(select(Chapter).where(Chapter.subject_id == sid).order_by(Chapter.number)).all()
    teachers = db.scalars(select(Staff).where(Staff.school_id == user.school_id)).all()
    return {
        "id": s.id, "name": s.name, "grade": s.grade, "can_manage": _can(user, "subjects.manage"),
        "teachers": [{"id": t.id, "name": t.name, "designation": t.designation} for t in teachers
                     if t.subjects and s.name in [p.strip() for p in t.subjects.split(",")]],
        "chapters": [{"id": c.id, "number": c.number, "title": c.title, "description": c.description} for c in chs],
    }


@router.post("/subjects/{sid}/chapters", status_code=201)
def add_chapter(sid: int, data: ChapterIn, user: User = Depends(need("subjects.manage")),
                db: Session = Depends(get_db)):
    get_owned(db, Subject, sid, user.school_id)
    c = Chapter(subject_id=sid, **data.model_dump())
    db.add(c)
    db.commit()
    return {"id": c.id}


@router.put("/chapters/{cid}")
def update_chapter(cid: int, data: ChapterIn, user: User = Depends(need("subjects.manage")),
                   db: Session = Depends(get_db)):
    c, _ = get_chapter(db, user, cid)
    for k, v in data.model_dump().items():
        setattr(c, k, v)
    db.commit()
    return {"id": c.id}


@router.delete("/chapters/{cid}", status_code=204)
def delete_chapter(cid: int, user: User = Depends(need("subjects.manage")), db: Session = Depends(get_db)):
    c, _ = get_chapter(db, user, cid)
    db.delete(c)
    db.commit()


# ---------- events ----------
def _event(e: Event) -> dict:
    return {"id": e.id, "title": e.title, "description": e.description, "date": e.date.isoformat(),
            "location": e.location, "category": e.category}


@router.get("/events")
def list_events(user: User = Depends(school_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Event).where(Event.school_id == user.school_id).order_by(Event.date.desc())).all()
    return {"items": [_event(e) for e in rows], "can_manage": _can(user, "content.manage")}


@router.post("/events", status_code=201)
def add_event(data: EventIn, user: User = Depends(need("content.manage")), db: Session = Depends(get_db)):
    e = Event(school_id=user.school_id, **data.model_dump())
    db.add(e)
    db.commit()
    return _event(e)


@router.put("/events/{eid}")
def update_event(eid: int, data: EventIn, user: User = Depends(need("content.manage")), db: Session = Depends(get_db)):
    e = get_owned(db, Event, eid, user.school_id)
    for k, v in data.model_dump().items():
        setattr(e, k, v)
    db.commit()
    return _event(e)


@router.delete("/events/{eid}", status_code=204)
def delete_event(eid: int, user: User = Depends(need("content.manage")), db: Session = Depends(get_db)):
    db.delete(get_owned(db, Event, eid, user.school_id))
    db.commit()


# ---------- gallery ----------
def _gal(g: GalleryItem) -> dict:
    return {"id": g.id, "title": g.title, "category": g.category, "caption": g.caption,
            "taken_on": g.taken_on.isoformat(), "has_image": bool(g.image), "image_v": storage.version(g.image)}


@router.get("/gallery")
def list_gallery(user: User = Depends(school_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(GalleryItem).where(GalleryItem.school_id == user.school_id)
                      .order_by(GalleryItem.taken_on.desc())).all()
    return {"items": [_gal(g) for g in rows], "can_manage": _can(user, "content.manage")}


@router.post("/gallery", status_code=201)
def add_gallery(data: GalleryIn, user: User = Depends(need("content.manage")), db: Session = Depends(get_db)):
    g = GalleryItem(school_id=user.school_id, **data.model_dump())
    db.add(g)
    db.commit()
    return _gal(g)


@router.put("/gallery/{gid}")
def update_gallery(gid: int, data: GalleryIn, user: User = Depends(need("content.manage")),
                   db: Session = Depends(get_db)):
    g = get_owned(db, GalleryItem, gid, user.school_id)
    for k, v in data.model_dump().items():
        setattr(g, k, v)
    db.commit()
    return _gal(g)


@router.delete("/gallery/{gid}", status_code=204)
def delete_gallery(gid: int, user: User = Depends(need("content.manage")), db: Session = Depends(get_db)):
    g = get_owned(db, GalleryItem, gid, user.school_id)
    storage.remove(g.image)
    db.delete(g)
    db.commit()


@router.get("/gallery/{gid}/image")
def gallery_image(gid: int, user: User = Depends(school_user), db: Session = Depends(get_db)):
    return storage.serve(get_owned(db, GalleryItem, gid, user.school_id).image)


@router.post("/gallery/{gid}/image", status_code=204)
async def set_gallery_image(gid: int, request: Request, user: User = Depends(need("content.manage")),
                            db: Session = Depends(get_db)):
    g = get_owned(db, GalleryItem, gid, user.school_id)
    data, ext = await storage.read_image(request)
    old = g.image
    g.image = storage.save(user.school_id, data, ext)
    db.commit()
    storage.remove(old)


# ---------- goals ----------
def _goal(g: Goal) -> dict:
    return {"id": g.id, "title": g.title, "description": g.description, "target_year": g.target_year,
            "progress": g.progress, "status": g.status}


@router.get("/goals")
def list_goals(user: User = Depends(school_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Goal).where(Goal.school_id == user.school_id).order_by(Goal.target_year)).all()
    return {"items": [_goal(g) for g in rows], "can_manage": _can(user, "content.manage")}


@router.post("/goals", status_code=201)
def add_goal(data: GoalIn, user: User = Depends(need("content.manage")), db: Session = Depends(get_db)):
    g = Goal(school_id=user.school_id, **data.model_dump())
    db.add(g)
    db.commit()
    return _goal(g)


@router.put("/goals/{gid}")
def update_goal(gid: int, data: GoalIn, user: User = Depends(need("content.manage")), db: Session = Depends(get_db)):
    g = get_owned(db, Goal, gid, user.school_id)
    for k, v in data.model_dump().items():
        setattr(g, k, v)
    db.commit()
    return _goal(g)


@router.delete("/goals/{gid}", status_code=204)
def delete_goal(gid: int, user: User = Depends(need("content.manage")), db: Session = Depends(get_db)):
    db.delete(get_owned(db, Goal, gid, user.school_id))
    db.commit()


# ---------- chatbot ----------
@router.post("/chat")
def chat(data: ChatIn, user: User = Depends(school_user), db: Session = Depends(get_db)):
    return chatbot.ask(db, user, data.question)


@router.get("/chat/history")
def chat_history(user: User = Depends(school_user), db: Session = Depends(get_db)):
    return {"messages": chatbot.history(db, user), "suggestions": chatbot.suggestions_for(user)}


@router.delete("/chat/history", status_code=204)
def chat_clear(user: User = Depends(school_user), db: Session = Depends(get_db)):
    chatbot.clear_history(db, user)
