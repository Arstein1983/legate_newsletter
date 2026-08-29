from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RecipientGroup(Base):
    __tablename__ = "recipient_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    recipients: Mapped[list["Recipient"]] = relationship(back_populates="group", cascade="all, delete-orphan")


class Recipient(Base):
    __tablename__ = "recipients"
    __table_args__ = (
        UniqueConstraint("group_id", "username", name="uq_group_username"),
        UniqueConstraint("group_id", "phone", name="uq_group_phone"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("recipient_groups.id", ondelete="CASCADE"))
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    group: Mapped["RecipientGroup"] = relationship(back_populates="recipients")


class MessageTemplate(Base):
    __tablename__ = "message_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255))
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    media_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("recipient_groups.id", ondelete="CASCADE"))
    template_id: Mapped[int] = mapped_column(ForeignKey("message_templates.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(32), default="running")
    total: Mapped[int] = mapped_column(Integer, default=0)
    sent: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    group: Mapped["RecipientGroup"] = relationship()
    template: Mapped["MessageTemplate"] = relationship()
    logs: Mapped[list["CampaignLog"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")


class CampaignLog(Base):
    __tablename__ = "campaign_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    recipient_id: Mapped[int] = mapped_column(ForeignKey("recipients.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(32))
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    campaign: Mapped["Campaign"] = relationship(back_populates="logs")
    recipient: Mapped["Recipient"] = relationship()


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))
