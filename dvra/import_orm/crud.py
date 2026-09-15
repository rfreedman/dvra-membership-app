"""Minimal CRUD helpers required by ``scripts.import_from_spreadsheet``."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from dvra.import_orm import models


def sync_member_membership_from_latest_payment(db: Session, member: models.Member, *, commit: bool = True) -> None:
    stmt = (
        select(models.Payment)
        .where(models.Payment.member_id == member.id)
        .where(models.Payment.membership_type_id.isnot(None))
        .order_by(models.Payment.payment_date.desc(), models.Payment.id.desc())
        .limit(1)
    )
    latest = db.execute(stmt).scalar_one_or_none()
    if latest is not None:
        member.membership_type_id = latest.membership_type_id
        db.add(member)
        if commit:
            db.commit()
        else:
            db.flush()
