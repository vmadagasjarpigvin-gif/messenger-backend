import asyncio
from database import async_session, init_db
from models import InviteCode

async def add_codes():
    await init_db()
    async with async_session() as session:
        codes = ["WELCOME123", "FRIEND456", "TEST789"]
        for code in codes:
            invite = InviteCode(code=code, is_used=False)
            session.add(invite)
        await session.commit()
        print(f"✅ Добавлены коды: {codes}")

if __name__ == "__main__":
    asyncio.run(add_codes())