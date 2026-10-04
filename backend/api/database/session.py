from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Generator

from api.config import settings


def get_database_urls() -> tuple[str, str]:
    """Return (sync_url, async_url) based on DATABASE_URL."""
    base_url = settings.DATABASE_URL
    
    if base_url.startswith("sqlite"):
        # SQLite for local development
        sync_url = base_url
        async_url = base_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return sync_url, async_url
    
    # PostgreSQL for production
    sync_url = base_url
    if base_url.startswith("postgresql://"):
        async_url = base_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    else:
        async_url = base_url
    return sync_url, async_url


sync_url, async_url = get_database_urls()

# SQLite needs StaticPool and check_same_thread=False
if sync_url.startswith("sqlite"):
    engine = create_engine(
        sync_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async_engine = create_async_engine(
        async_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    engine = create_engine(sync_url, pool_pre_ping=True)
    async_engine = create_async_engine(async_url, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = async_sessionmaker(
    autocommit=False, autoflush=False, bind=async_engine, class_=AsyncSession
)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def init_db() -> None:
    from api.database.base import Base
    from api.database import models
    Base.metadata.create_all(bind=engine)