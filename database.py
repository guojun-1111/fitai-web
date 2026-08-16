# SPDX-FileCopyrightText: 2026 Chen Guojun
# SPDX-License-Identifier: AGPL-3.0-or-later

"""SQLAlchemy async engine + session factory"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from config import DATABASE_PATH, DATABASE_URL as _CONFIG_DATABASE_URL

DATABASE_URL = _CONFIG_DATABASE_URL or f"sqlite+aiosqlite:///{DATABASE_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    # Import all models so Base.metadata knows about them
    import models.user     # noqa
    import models.setting  # noqa
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
