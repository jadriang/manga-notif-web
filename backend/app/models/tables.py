from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clerk_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True)
    telegram_link_token: Mapped[Optional[str]] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Manga(Base):
    __tablename__ = "manga"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    asura_slug: Mapped[Optional[str]] = mapped_column(String(500))
    demonic_slug: Mapped[Optional[str]] = mapped_column(String(500))
    cover_url: Mapped[Optional[str]] = mapped_column(Text)
    added_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="manga", cascade="all, delete-orphan")
    chapter_states: Mapped[list[ChapterState]] = relationship(back_populates="manga", cascade="all, delete-orphan")


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("user_id", "manga_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    manga_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("manga.id"), nullable=False)
    notify: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="subscriptions")
    manga: Mapped[Manga] = relationship(back_populates="subscriptions")


class ChapterState(Base):
    __tablename__ = "chapter_state"
    __table_args__ = (UniqueConstraint("manga_id", "site"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    manga_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("manga.id"), nullable=False)
    site: Mapped[str] = mapped_column(String(20), nullable=False)
    latest_chapter: Mapped[str] = mapped_column(String(20), nullable=False)
    chapter_url: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    manga: Mapped[Manga] = relationship(back_populates="chapter_states")


class InviteCode(Base):
    __tablename__ = "invite_codes"
    __table_args__ = (CheckConstraint("used_count <= max_uses", name="used_count_le_max"),)

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
