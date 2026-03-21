import asyncio
from database import async_session
from models import InviteCode
from sqlalchemy import select

async def check_codes():
    async with async_session() as session:
        result = await session.execute(select(InviteCode))
        codes = result.scalars().all()
        
        if not codes:
            print("❌ Нет ни одного инвайт-кода в базе!")
        else:
            print("📋 Инвайт-коды в базе:")
            for code in codes:
                status = "✅ свободен" if not code.is_used else "❌ использован"
                print(f"   {code.code} - {status}")

if __name__ == "__main__":
    asyncio.run(check_codes())