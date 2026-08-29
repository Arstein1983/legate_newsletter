from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import AppSetting, Campaign, CampaignLog, MessageTemplate, Recipient, RecipientGroup


async def create_group(session: AsyncSession, name: str) -> RecipientGroup:
    group = RecipientGroup(name=name.strip())
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def list_groups(session: AsyncSession) -> Sequence[tuple[RecipientGroup, int]]:
    stmt = (
        select(RecipientGroup, func.count(Recipient.id))
        .outerjoin(Recipient)
        .group_by(RecipientGroup.id)
        .order_by(RecipientGroup.id.desc())
    )
    rows = (await session.execute(stmt)).all()
    return [(row[0], int(row[1])) for row in rows]


async def get_group(session: AsyncSession, group_id: int) -> Optional[RecipientGroup]:
    return await session.get(RecipientGroup, group_id)


async def delete_group(session: AsyncSession, group_id: int) -> None:
    group = await session.get(RecipientGroup, group_id)
    if group:
        await session.delete(group)
        await session.commit()


async def add_recipient(
    session: AsyncSession,
    group_id: int,
    username: Optional[str],
    phone: Optional[str],
    display_name: Optional[str] = None,
) -> tuple[Optional[Recipient], str]:
    if username:
        exists = await session.scalar(
            select(Recipient).where(Recipient.group_id == group_id, Recipient.username == username)
        )
        if exists:
            return None, "duplicate"
    if phone:
        exists = await session.scalar(
            select(Recipient).where(Recipient.group_id == group_id, Recipient.phone == phone)
        )
        if exists:
            return None, "duplicate"

    recipient = Recipient(group_id=group_id, username=username, phone=phone, display_name=display_name)
    session.add(recipient)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return None, "duplicate"
    await session.refresh(recipient)
    return recipient, "ok"


async def list_recipients(
    session: AsyncSession, group_id: int, offset: int = 0, limit: int = 8
) -> tuple[Sequence[Recipient], int]:
    total = await session.scalar(select(func.count(Recipient.id)).where(Recipient.group_id == group_id)) or 0
    rows = (
        await session.scalars(
            select(Recipient)
            .where(Recipient.group_id == group_id)
            .order_by(Recipient.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return rows, int(total)


async def get_all_recipients(session: AsyncSession, group_id: int) -> Sequence[Recipient]:
    return (
        await session.scalars(select(Recipient).where(Recipient.group_id == group_id).order_by(Recipient.id))
    ).all()


async def delete_recipient(session: AsyncSession, recipient_id: int) -> Optional[int]:
    recipient = await session.get(Recipient, recipient_id)
    if not recipient:
        return None
    group_id = recipient.group_id
    await session.delete(recipient)
    await session.commit()
    return group_id


async def create_template(
    session: AsyncSession,
    title: str,
    text: Optional[str],
    media_path: Optional[str],
    media_type: Optional[str],
) -> MessageTemplate:
    template = MessageTemplate(title=title.strip(), text=text, media_path=media_path, media_type=media_type)
    session.add(template)
    await session.commit()
    await session.refresh(template)
    return template


async def list_templates(session: AsyncSession) -> Sequence[MessageTemplate]:
    return (await session.scalars(select(MessageTemplate).order_by(MessageTemplate.id.desc()))).all()


async def get_template(session: AsyncSession, template_id: int) -> Optional[MessageTemplate]:
    return await session.get(MessageTemplate, template_id)


async def delete_template(session: AsyncSession, template_id: int) -> Optional[MessageTemplate]:
    template = await session.get(MessageTemplate, template_id)
    if not template:
        return None
    await session.delete(template)
    await session.commit()
    return template


async def create_campaign(session: AsyncSession, group_id: int, template_id: int, total: int) -> Campaign:
    campaign = Campaign(group_id=group_id, template_id=template_id, status="running", total=total)
    session.add(campaign)
    await session.commit()
    await session.refresh(campaign)
    return campaign


async def get_campaign(session: AsyncSession, campaign_id: int) -> Optional[Campaign]:
    return await session.get(Campaign, campaign_id)


async def update_campaign_progress(
    session: AsyncSession,
    campaign_id: int,
    *,
    sent: Optional[int] = None,
    failed: Optional[int] = None,
    status: Optional[str] = None,
    finished: bool = False,
) -> None:
    campaign = await session.get(Campaign, campaign_id)
    if not campaign:
        return
    if sent is not None:
        campaign.sent = sent
    if failed is not None:
        campaign.failed = failed
    if status is not None:
        campaign.status = status
    if finished:
        campaign.finished_at = datetime.now()
    await session.commit()


async def add_campaign_log(
    session: AsyncSession,
    campaign_id: int,
    recipient_id: int,
    status: str,
    error: Optional[str] = None,
) -> None:
    session.add(CampaignLog(campaign_id=campaign_id, recipient_id=recipient_id, status=status, error=error))
    await session.commit()


async def list_campaigns(session: AsyncSession, limit: int = 10) -> Sequence[Campaign]:
    stmt = (
        select(Campaign)
        .options(selectinload(Campaign.group), selectinload(Campaign.template))
        .order_by(desc(Campaign.id))
        .limit(limit)
    )
    return (await session.scalars(stmt)).all()


async def get_setting(session: AsyncSession, key: str, default: str) -> str:
    row = await session.get(AppSetting, key)
    return row.value if row else default


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(AppSetting, key)
    if row:
        row.value = value
    else:
        session.add(AppSetting(key=key, value=value))
    await session.commit()
