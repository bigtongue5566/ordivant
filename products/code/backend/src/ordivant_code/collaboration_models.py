from datetime import datetime
from sqlalchemy import DateTime, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class CollaborationAttachment(Base):
    __tablename__ = "collaboration_attachments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resource_kind: Mapped[str] = mapped_column(String(32), index=True)
    resource_id: Mapped[str] = mapped_column(String(36), index=True)
    actor_id: Mapped[str] = mapped_column(String(36))
    filename: Mapped[str] = mapped_column(String(160))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CollaborationSubscription(Base):
    __tablename__ = "collaboration_subscriptions"
    __table_args__ = (UniqueConstraint("resource_kind", "resource_id", "principal_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    resource_kind: Mapped[str] = mapped_column(String(32), index=True)
    resource_id: Mapped[str] = mapped_column(String(36), index=True)
    principal_id: Mapped[str] = mapped_column(String(36), index=True)


class CollaborationNotification(Base):
    __tablename__ = "collaboration_notifications"
    __table_args__ = (UniqueConstraint("event_id", "principal_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(160))
    resource_kind: Mapped[str] = mapped_column(String(32), index=True)
    resource_id: Mapped[str] = mapped_column(String(36), index=True)
    principal_id: Mapped[str] = mapped_column(String(36), index=True)
    # A verified upstream webhook has no local human/Agent identity.
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event: Mapped[str] = mapped_column(String(80))
    body: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CollaborationMutation(Base):
    __tablename__ = "collaboration_mutations"
    __table_args__ = (UniqueConstraint("principal_id", "key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    principal_id: Mapped[str] = mapped_column(String(36))
    key: Mapped[str] = mapped_column(String(160))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_json: Mapped[str] = mapped_column(Text)
