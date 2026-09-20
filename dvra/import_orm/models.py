from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dvra.import_orm.database import Base


class LicenseClass(Base):
    __tablename__ = "license_classes"
    __table_args__ = (UniqueConstraint("name", name="uq_license_class_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class MembershipType(Base):
    __tablename__ = "membership_types"
    __table_args__ = (UniqueConstraint("name", name="uq_membership_type_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AdminUser(Base):
    __tablename__ = "admin_users"
    __table_args__ = (UniqueConstraint("username", name="uq_admin_user_username"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Manager(Base):
    __tablename__ = "managers"
    __table_args__ = (UniqueConstraint("username", name="uq_manager_username"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Member(Base):
    __tablename__ = "members"
    __table_args__ = (
        Index(
            "uq_members_call_sign_when_set",
            "call_sign",
            unique=True,
            sqlite_where=text("call_sign IS NOT NULL"),
            postgresql_where=text("call_sign IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    last_name: Mapped[str] = mapped_column(String(128), nullable=False)
    first_name: Mapped[str] = mapped_column(String(128), nullable=False)
    call_sign: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    nickname: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    qrz_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    #: Mailing address from roster column **O** / forms; split via ``parse_roster_us_address`` on import & paste-friendly entry.
    address_street: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address_city: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address_state: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    address_zip: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    license_class_id: Mapped[Optional[int]] = mapped_column(ForeignKey("license_classes.id"), nullable=True)
    membership_type_id: Mapped[Optional[int]] = mapped_column(ForeignKey("membership_types.id"), nullable=True)
    family_primary_member_id: Mapped[Optional[int]] = mapped_column(ForeignKey("members.id"), nullable=True)
    arrl_member: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deceased: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    key_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    paid_through: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    payments: Mapped[list["Payment"]] = relationship(
        "Payment",
        back_populates="member",
        cascade="all, delete-orphan",
        order_by="Payment.payment_date.desc()",
    )
    license_class: Mapped[Optional[LicenseClass]] = relationship("LicenseClass")
    membership_type: Mapped[Optional[MembershipType]] = relationship("MembershipType")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"), nullable=False, index=True)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    paid_through: Mapped[date] = mapped_column(Date, nullable=False)
    membership_type_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("membership_types.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    #: Payment / ARRL form reference parsed from roster cell text, e.g. trailing ``(12345)``.
    form_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    #: Explicit membership year this payment covers (paid_through is Dec 31 of this year).
    membership_year: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    member: Mapped[Member] = relationship("Member", back_populates="payments")
    membership_type: Mapped[Optional[MembershipType]] = relationship("MembershipType")
