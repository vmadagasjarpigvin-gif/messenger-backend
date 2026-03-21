import asyncio
from database import async_session
from models import InviteCode

async def add_codes():
    async with async_session() as session:
        codes = [
            "WELCOME123",
            "FRIEND456", 
            "TEST789",
            "CODE001",
            "CODE002",
            "MESSENGER"
        ]
        
        for code in codes:
            invite = InviteCode(code=code, is_used=False)
            session.add(invite)
        
        await session.commit()
        print(f"✅ Добавлены коды: {codes}")

if __name__ == "__main__":
    asyncio.run(add_codes())