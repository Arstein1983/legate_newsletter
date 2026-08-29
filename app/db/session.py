from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.models import AppSetting, Base

engine = create_async_engine(
    get_settings().database_url, echo=False, pool_pre_ping=True, pool_recycle=3600
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    settings = get_settings()
    async with SessionLocal() as session:
        existing = await session.get(AppSetting, "send_delay_seconds")
        if existing is None:
            session.add(AppSetting(key="send_delay_seconds", value=str(settings.send_delay_seconds)))
            await session.commit()
