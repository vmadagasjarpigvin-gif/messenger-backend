from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from models import Base
import os
from dotenv import load_dotenv

load_dotenv()

# Явно указываем asyncpg драйвер
# Render предоставит переменную окружения DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/messenger")

# Создаём асинхронный движок. NullPool отключает пул соединений,
# что может быть полезно для бесплатного тарифа Render.
engine = create_async_engine(DATABASE_URL, echo=True, poolclass=NullPool)

# Создаём фабрику асинхронных сессий
async_session = sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

async def init_db():
    """Создаёт все таблицы в базе данных, если они не существуют."""
    async with engine.begin() as conn:
        # run_sync используется для выполнения синхронных операций (создание таблиц) в асинхронном контексте
        await conn.run_sync(Base.metadata.create_all)
