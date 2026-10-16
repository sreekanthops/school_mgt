"""Subscription billing in the Platform Console: invoices, marking them paid (which extends the subscription), and
renewal tracking. Owners can view and download their own school's invoices, read-only.

Invoices carry no foreign key to the school (like the audit trail) so billing history survives school deletion.

Pricing model (annual, before 18 % GST):
  • Free     – ₹0 regardless of strength (demo / micro schools, hard-capped at 50 students)
  • Starter  – strength-based; see STARTER_TIERS
  • Standard – strength-based; see STANDARD_TIERS
  • Premium  – strength-based; see PREMIUM_TIERS

  Each tier is (max_students_inclusive, annual_price_inr).  The last entry covers "anything above".
  Monthly billing = annual / 10  (effectively 2 months free vs paying month-by-month).
  The superadmin can always override the amount on any individual invoice.
"""
import secrets
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Invoice, School, User
from ..reports import (BODY, H1, H2, SUB, Paragraph, Spacer, build, csv_response, escape, kv_table, mm, pdf_response, rs)
from ..security import school_user, subscription_info, superadmin_only
from .platform import audit

router = APIRouter(prefix="/api")

# ---------------------------------------------------------------------------
# Strength-based pricing  (annual, INR, before tax)
# Each row: (upper_bound_inclusive, annual_price).  Last row = open-ended upper bound.
# ---------------------------------------------------------------------------
_STARTER_TIERS  = [(200, 15000), (500, 30000), (1000, 50000), (2000, 80000), (999999, 120000)]
_STANDARD_TIERS = [(200, 22000), (500, 45000), (1000, 75000), (2000, 120000), (999999, 180000)]
_PREMIUM_TIERS  = [(200, 35000), (500, 70000), (1000, 120000), (2000, 190000), (999999, 280000)]

_PLAN_TIERS: dict[str, list[tuple[int, int]]] = {
    "Free":     [],               # always 0
    "Starter":  _STARTER_TIERS,
    "Standard": _STANDARD_TIERS,
    "Premium":  _PREMIUM_TIERS,
}

# Ordered strength band labels for the UI pricing table
STRENGTH_BANDS = ["Up to 200", "201–500", "501–1,000", "1,001–2,000", "2,001+"]


def plan_price(plan: str, max_students: int, monthly: bool = False) -> int:
    """Return the suggested price (INR, before tax) for the given plan and school strength.

    *monthly* – if True, return the monthly price (annual / 10); if False, return annual.
    The superadmin may still override this on any individual invoice.
    """
    tiers = _PLAN_TIERS.get(plan, [])
    if not tiers:
        return 0
    annual = next((price for cap, price in tiers if max_students <= cap), tiers[-1][1])
    return round(annual / 10) if monthly else annual


def pricing_table() -> list[dict]:
    """Return the full pricing matrix for all plans × bands (used by the UI)."""
    rows = []
    plans = ["Starter", "Standard", "Premium"]
    for i, (cap, label) in enumerate(zip(
        [200, 500, 1000, 2000, 999999],
        STRENGTH_BANDS,
    )):
        rows.append({
            "band": label,
            "plans": {p: _PLAN_TIERS[p][i][1] for p in plans},
        })
    return rows


DEFAULT_TAX_PCT = 18.0
DEFAULT_DUE_DAYS = 15
MODES = ("Bank Transfer", "UPI", "Cheque", "Cash", "Card")
SELLER = "School Management Platform"
# Legacy alias kept so existing code that reads PLAN_PRICE still compiles.
PLAN_PRICE = {"Free": 0, "Starter": 22000, "Standard": 45000, "Premium": 70000}  # rough mid-tier fallback


class InvoiceIn(BaseModel):
    period_start: Optional[date] = None   # default: the day after the current subscription ends (or today)
    period_end: Optional[date] = None     # default: one year after period_start, less a day
    amount: Optional[float] = Field(default=None, ge=0, le=100_000_000)  # default: the plan price
    tax_pct: float = Field(default=DEFAULT_TAX_PCT, ge=0, le=100)
    due_on: Optional[date] = None
    note: Optional[str] = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _order(self):
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValueError("period end is before period start")
        return self


class PayIn(BaseModel):
    mode: str
    reference: Optional[str] = Field(default=None, max_length=60)
    paid_on: Optional[date] = None
    extend: bool = True  # move the school's subscription end date to the end of the invoice period

    @model_validator(mode="after")
    def _mode(self):
        if self.mode not in MODES:
            raise ValueError("invalid payment mode")
        return self


def _status(i: Invoice) -> str:
    return "Overdue" if i.status == "Pending" and i.due_on < date.today() else i.status


def _out(i: Invoice) -> dict:
    return {"id": i.id, "number": i.number, "school_id": i.school_id, "school_name": i.school_name, "plan": i.plan,
            "period_start": i.period_start.isoformat(), "period_end": i.period_end.isoformat(), "amount": i.amount,
            "tax": i.tax, "total": i.total, "status": _status(i), "issued_on": i.issued_on.isoformat(),
            "due_on": i.due_on.isoformat(), "paid_on": i.paid_on.isoformat() if i.paid_on else None,
            "mode": i.mode, "reference": i.reference, "note": i.note}


def _get(db: Session, iid: int) -> Invoice:
    i = db.get(Invoice, iid)
    if not i:
        raise HTTPException(404, "Not found")
    return i


def _school(db: Session, sid: int) -> School:
    s = db.get(School, sid)
    if not s:
        raise HTTPException(404, "Not found")
    return s


def _year_from(start: date) -> date:
    """Last day of a one-year service period that begins on `start`."""
    try:
        return start.replace(year=start.year + 1) - timedelta(days=1)
    except ValueError:  # 29 February
        return start.replace(year=start.year + 1, day=28)


def _next_period(s: School) -> tuple[date, date]:
    """A renewal starts the day after the current subscription ends (or today if it already ended)."""
    today = date.today()
    start = s.subscription_end + timedelta(days=1) if s.subscription_end and s.subscription_end >= today else today
    return start, _year_from(start)


# ---------- superadmin ----------
@router.get("/billing/summary")
def summary(_: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    invs = db.scalars(select(Invoice)).all()
    paid = [i for i in invs if i.status == "Paid"]
    pending = [i for i in invs if i.status == "Pending"]
    overdue = [i for i in pending if i.due_on < date.today()]
    by_month: dict[str, float] = defaultdict(float)
    for i in paid:
        by_month[i.paid_on.strftime("%Y-%m")] += i.total
    y, m, months = date.today().year, date.today().month, []
    for _n in range(12):
        months.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    # renewal tracking: every school, nearest end date first, with whether a renewal invoice is already open
    open_for = {i.school_id for i in pending}
    renewals = []
    for s in db.scalars(select(School).order_by(School.id)):
        info = subscription_info(s.subscription_end)
        suggested = plan_price(s.plan, s.max_students)
        renewals.append({"school_id": s.id, "school": s.name, "plan": s.plan, "active": s.active, "end": info["end"],
                         "days_left": info["days_left"], "status": info["status"], "invoice_open": s.id in open_for,
                         "max_students": s.max_students, "suggested_price": suggested})
    renewals.sort(key=lambda r: (r["days_left"] is None, r["days_left"] if r["days_left"] is not None else 0))
    return {
        "collected": round(sum(i.total for i in paid), 2), "pending": round(sum(i.total for i in pending), 2),
        "overdue": round(sum(i.total for i in overdue), 2), "overdue_count": len(overdue),
        "invoices": len(invs), "monthly": [{"month": k, "amount": round(by_month.get(k, 0), 2)} for k in reversed(months)],
        "renewals": renewals,
        "due_soon": [r for r in renewals if r["days_left"] is not None and r["days_left"] <= 30 and not r["invoice_open"]],
        "plan_prices": PLAN_PRICE, "tax_pct": DEFAULT_TAX_PCT,
        "pricing_table": pricing_table(),
    }


@router.get("/invoices")
def list_invoices(school_id: Optional[int] = None, status: Optional[str] = Query(None, max_length=10),
                  _: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    stmt = select(Invoice).order_by(Invoice.id.desc()).limit(500)
    if school_id:
        stmt = stmt.where(Invoice.school_id == school_id)
    rows = [_out(i) for i in db.scalars(stmt)]
    return [r for r in rows if not status or r["status"] == status]


@router.post("/schools/{school_id}/invoices", status_code=201)
def create_invoice(school_id: int, data: InvoiceIn, sa: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    s = _school(db, school_id)
    start = data.period_start or _next_period(s)[0]
    end = data.period_end or _year_from(start)
    if end < start:
        raise HTTPException(422, "The period ends before it starts")
    amount = round(plan_price(s.plan, s.max_students) if data.amount is None else data.amount, 2)
    tax = round(amount * data.tax_pct / 100, 2)
    i = Invoice(number=f"TMP-{secrets.token_hex(6)}", school_id=s.id, school_name=s.name, plan=s.plan, period_start=start,
                period_end=end, amount=amount, tax=tax, total=round(amount + tax, 2), issued_on=date.today(),
                due_on=data.due_on or date.today() + timedelta(days=DEFAULT_DUE_DAYS), note=data.note)
    db.add(i)
    db.flush()
    i.number = f"INV-{date.today().year}-{i.id:05d}"
    audit(db, sa, "invoice_created", s, f"{i.number} for {i.total}")
    db.commit()
    return _out(i)


@router.get("/schools/{school_id}/billing/price")
def school_suggested_price(school_id: int, _: User = Depends(superadmin_only),
                           db: Session = Depends(get_db)):
    """Suggested annual invoice amount for a school, based on its plan and student limit."""
    s = _school(db, school_id)
    return {
        "plan": s.plan, "max_students": s.max_students,
        "suggested_annual": plan_price(s.plan, s.max_students),
        "suggested_monthly": plan_price(s.plan, s.max_students, monthly=True),
        "tax_pct": DEFAULT_TAX_PCT,
    }


@router.put("/invoices/{iid}/pay")
def mark_paid(iid: int, data: PayIn, sa: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    i = _get(db, iid)
    if i.status != "Pending":
        raise HTTPException(409, f"This invoice is already {i.status.lower()}")
    i.status, i.paid_on, i.mode, i.reference = "Paid", data.paid_on or date.today(), data.mode, data.reference
    s = db.get(School, i.school_id)
    renewed = ""
    if s and data.extend and (not s.subscription_end or i.period_end > s.subscription_end):
        s.subscription_end = i.period_end
        renewed = f"; subscription now ends {i.period_end.isoformat()}"
    audit(db, sa, "invoice_paid", s, f"{i.number} paid by {data.mode}{renewed}")
    db.commit()
    return _out(i)


@router.put("/invoices/{iid}/cancel")
def cancel_invoice(iid: int, sa: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    i = _get(db, iid)
    if i.status != "Pending":
        raise HTTPException(409, "Only an unpaid invoice can be cancelled")
    i.status = "Cancelled"
    audit(db, sa, "invoice_cancelled", db.get(School, i.school_id), i.number)
    db.commit()
    return _out(i)


@router.get("/invoices/export")
def export_invoices(_: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    rows = [_out(i) for i in db.scalars(select(Invoice).order_by(Invoice.id.desc()))]
    return csv_response(["Invoice", "School", "Plan", "Period start", "Period end", "Amount", "Tax", "Total", "Status",
                         "Issued", "Due", "Paid on", "Mode", "Reference"],
                        [[r["number"], r["school_name"], r["plan"], r["period_start"], r["period_end"], r["amount"], r["tax"],
                          r["total"], r["status"], r["issued_on"], r["due_on"], r["paid_on"], r["mode"], r["reference"]] for r in rows],
                        "invoices")


def _pdf(db: Session, i: Invoice) -> bytes:
    s = db.get(School, i.school_id)
    st = _status(i)
    place = ", ".join(x for x in (s.address if s else None, s.city if s else None, s.state if s else None) if x)
    story = [Paragraph(escape(SELLER), H1), Paragraph("Tax invoice for school software subscription", SUB),
             kv_table([("Invoice no.", i.number), ("Status", st), ("Issued", i.issued_on.strftime("%d %b %Y")),
                       ("Due", i.due_on.strftime("%d %b %Y")), ("Billed to", i.school_name),
                       *([("Address", place)] if place else []), ("Plan", i.plan),
                       ("Service period", f"{i.period_start:%d %b %Y} to {i.period_end:%d %b %Y}")]),
             Paragraph("Amount", H2),
             kv_table([("Subscription", rs(i.amount)), (f"Tax ({round(i.tax * 100 / i.amount) if i.amount else 0}%)", rs(i.tax)),
                       ("Total", rs(i.total))])]
    if i.status == "Paid":
        story += [Paragraph("Payment", H2), kv_table([("Paid on", i.paid_on.strftime("%d %b %Y")), ("Mode", i.mode or "-"),
                                                      ("Reference", i.reference or "-")])]
    if i.note:
        story += [Paragraph("Note", H2), Paragraph(escape(i.note), BODY)]
    story += [Spacer(1, 8 * mm), Paragraph("This is a computer generated invoice.", SUB)]
    return build(story, SELLER)


@router.get("/invoices/{iid}/pdf")
def invoice_pdf(iid: int, _: User = Depends(superadmin_only), db: Session = Depends(get_db)):
    i = _get(db, iid)
    return pdf_response(_pdf(db, i), i.number)


# ---------- the school owner, read-only ----------
def _owner(user: User = Depends(school_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Only the school owner can see billing")
    return user


@router.get("/billing/mine")
def my_billing(user: User = Depends(_owner), db: Session = Depends(get_db)):
    s = db.get(School, user.school_id)
    rows = db.scalars(select(Invoice).where(Invoice.school_id == user.school_id, Invoice.status != "Cancelled")
                      .order_by(Invoice.id.desc())).all()
    return {"plan": s.plan, "subscription": subscription_info(s.subscription_end), "invoices": [_out(i) for i in rows]}


@router.get("/billing/mine/{iid}/pdf")
def my_invoice_pdf(iid: int, user: User = Depends(_owner), db: Session = Depends(get_db)):
    i = _get(db, iid)
    if i.school_id != user.school_id or i.status == "Cancelled":
        raise HTTPException(404, "Not found")
    return pdf_response(_pdf(db, i), i.number)
