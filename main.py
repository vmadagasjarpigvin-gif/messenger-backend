from fastapi import FastAPI, WebSocket, Depends, HTTPException, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import async_session, init_db
from models import User, PreKey, InviteCode
from schemas import UserRegister, UserResponse, PreKeyBundle, NewPreKeys, Token
from auth import create_access_token, verify_token
from websocket_manager import manager
import json
import os
import logging
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Защищённый мессенджер",
    description="E2EE мессенджер с WebRTC звонками",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# ========== НАСТРОЙКА CORS ==========
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",  # Для разработки разрешаем всё
        "https://*.ngrok-free.dev",
        "http://localhost:8000",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# ========== ЗАВИСИМОСТИ ==========
async def get_db():
    async with async_session() as session:
        yield session

# ========== СТАРТАП ==========
@app.on_event("startup")
async def startup():
    """Запускается при старте сервера"""
    logger.info("🚀 Запуск сервера...")
    await init_db()
    logger.info("✅ База данных инициализирована")

@app.on_event("shutdown")
async def shutdown():
    """Запускается при остановке сервера"""
    logger.info("👋 Сервер остановлен")

# ========== ЗДОРОВЬЕ СЕРВЕРА ==========
@app.get("/")
async def root():
    return {
        "name": "Защищённый мессенджер",
        "version": "1.0.0",
        "status": "online",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/health")
async def health():
    return {"status": "healthy"}

# ========== ЭНДПОИНТЫ API ==========

@app.post("/register", response_model=Token, status_code=201)
async def register(user_data: UserRegister, db: AsyncSession = Depends(get_db)):
    """Регистрация нового пользователя"""
    
    logger.info(f"📝 Попытка регистрации: {user_data.username}")
    
    # 1. Проверяем инвайт-код
    stmt = select(InviteCode).where(
        InviteCode.code == user_data.invite_code, 
        InviteCode.is_used == False
    )
    result = await db.execute(stmt)
    invite = result.scalar_one_or_none()
    if not invite:
        logger.warning(f"❌ Неверный инвайт-код: {user_data.invite_code}")
        raise HTTPException(status_code=400, detail="Неверный или уже использованный код")

    # 2. Проверяем, не занято ли имя
    stmt = select(User).where(User.username == user_data.username)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        logger.warning(f"❌ Имя занято: {user_data.username}")
        raise HTTPException(status_code=400, detail="Имя пользователя уже занято")

    # 3. Создаём пользователя
    new_user = User(
        username=user_data.username,
        identity_public_key=user_data.identity_public_key,
        invite_code_used=user_data.invite_code
    )
    db.add(new_user)
    await db.flush()

    # 4. Добавляем prekeys
    for pk in user_data.prekeys:
        prekey = PreKey(user_id=new_user.id, public_key=pk)
        db.add(prekey)

    # 5. Помечаем инвайт-код как использованный
    invite.is_used = True
    await db.commit()

    # 6. Создаём JWT-токен
    token = create_access_token({"sub": str(new_user.id)})
    
    logger.info(f"✅ Пользователь зарегистрирован: {user_data.username} (id: {new_user.id})")
    return {"access_token": token, "token_type": "bearer"}

@app.get("/users", response_model=list[UserResponse])
async def list_users(db: AsyncSession = Depends(get_db)):
    """Получить список всех пользователей"""
    stmt = select(User)
    result = await db.execute(stmt)
    users = result.scalars().all()
    logger.info(f"📋 Запрошен список пользователей: {len(users)}")
    return users

@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    """Получить информацию о пользователе"""
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user

@app.get("/user/{user_id}/bundle", response_model=PreKeyBundle)
async def get_bundle(user_id: int, db: AsyncSession = Depends(get_db)):
    """Получить набор ключей для начала диалога"""
    
    logger.info(f"🔑 Запрос bundle для пользователя {user_id}")
    
    # Находим пользователя
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Берём первый неиспользованный prekey
    stmt = select(PreKey).where(
        PreKey.user_id == user_id, 
        PreKey.is_used == False
    ).order_by(PreKey.id).limit(1)
    result = await db.execute(stmt)
    prekey = result.scalar_one_or_none()
    if not prekey:
        raise HTTPException(status_code=404, detail="Нет доступных ключей")

    # Помечаем prekey как использованный
    prekey.is_used = True
    await db.commit()

    return PreKeyBundle(
        user_id=user.id,
        identity_public_key=user.identity_public_key,
        prekey_public_key=prekey.public_key
    )

@app.post("/user/{user_id}/prekeys")
async def add_prekeys(user_id: int, prekeys_data: NewPreKeys, db: AsyncSession = Depends(get_db)):
    """Добавить новые prekeys (когда старые закончились)"""
    
    # Проверяем, существует ли пользователь
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # Добавляем новые prekeys
    for pk in prekeys_data.prekeys:
        prekey = PreKey(user_id=user_id, public_key=pk)
        db.add(prekey)
    await db.commit()
    logger.info(f"📝 Добавлены prekeys для пользователя {user_id}")
    return {"status": "ok"}

# ========== WEBSOCKET ДЛЯ СООБЩЕНИЙ ==========

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    """WebSocket для обмена сообщениями"""
    
    # Получаем токен из query-параметра
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Нет токена")
        return
    
    # Проверяем токен
    authenticated_user_id = verify_token(token)
    if authenticated_user_id != user_id:
        await websocket.close(code=1008, reason="Неверный токен")
        return

    # Подключаем пользователя
    await manager.connect(user_id, websocket)
    logger.info(f"🔌 Пользователь {user_id} подключился")
    
    try:
        while True:
            # Ждём сообщение от клиента
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")

            if msg_type == "message":
                # Пересылаем сообщение получателю
                to_user = message.get("to")
                encrypted_data = message.get("data")
                if to_user and encrypted_data:
                    await manager.send_personal_message({
                        "type": "message",
                        "from": user_id,
                        "data": encrypted_data,
                        "timestamp": datetime.now().isoformat()
                    }, to_user)
                    logger.info(f"💬 Сообщение от {user_id} к {to_user}")

            elif msg_type in ("offer", "answer", "candidate"):
                # Сигнальные сообщения для WebRTC (звонки)
                to_user = message.get("to")
                if to_user:
                    await manager.send_personal_message({
                        "type": msg_type,
                        "from": user_id,
                        "payload": message.get("payload")
                    }, to_user)
                    logger.info(f"📞 Сигнал {msg_type} от {user_id} к {to_user}")

            else:
                logger.warning(f"⚠️ Неизвестный тип сообщения: {msg_type}")

    except WebSocketDisconnect:
        manager.disconnect(user_id)
        logger.info(f"🔌 Пользователь {user_id} отключился")