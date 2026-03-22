from fastapi import FastAPI, WebSocket, Depends, HTTPException, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import select
from database import SessionLocal, init_db
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Защищённый мессенджер")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Зависимость для получения сессии базы данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.on_event("startup")
async def startup():
    logger.info("🚀 Запуск сервера...")
    init_db()
    logger.info("✅ База данных инициализирована")

@app.get("/")
async def root():
    return {
        "name": "Защищённый мессенджер",
        "version": "1.0.0",
        "status": "online",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/register", response_model=Token)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    logger.info(f"📝 Попытка регистрации: {user_data.username}")
    
    # Проверяем инвайт-код
    invite = db.query(InviteCode).filter(
        InviteCode.code == user_data.invite_code,
        InviteCode.is_used == False
    ).first()
    
    if not invite:
        raise HTTPException(status_code=400, detail="Неверный или уже использованный код")
    
    # Проверяем имя
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Имя пользователя уже занято")
    
    # Создаём пользователя
    new_user = User(
        username=user_data.username,
        identity_public_key=user_data.identity_public_key,
        invite_code_used=user_data.invite_code
    )
    db.add(new_user)
    db.flush()
    
    # Добавляем prekeys
    for pk in user_data.prekeys:
        prekey = PreKey(user_id=new_user.id, public_key=pk)
        db.add(prekey)
    
    # Помечаем инвайт-код как использованный
    invite.is_used = True
    db.commit()
    
    # Создаём JWT-токен
    token = create_access_token({"sub": str(new_user.id)})
    logger.info(f"✅ Пользователь зарегистрирован: {user_data.username}")
    return {"access_token": token, "token_type": "bearer"}

@app.get("/users", response_model=list[UserResponse])
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return users

@app.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user

@app.get("/user/{user_id}/bundle", response_model=PreKeyBundle)
def get_bundle(user_id: int, db: Session = Depends(get_db)):
    logger.info(f"🔑 Запрос bundle для пользователя {user_id}")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    prekey = db.query(PreKey).filter(
        PreKey.user_id == user_id,
        PreKey.is_used == False
    ).order_by(PreKey.id).first()
    
    if not prekey:
        raise HTTPException(status_code=404, detail="Нет доступных ключей")
    
    prekey.is_used = True
    db.commit()
    
    return PreKeyBundle(
        user_id=user.id,
        identity_public_key=user.identity_public_key,
        prekey_public_key=prekey.public_key
    )

@app.post("/user/{user_id}/prekeys")
def add_prekeys(user_id: int, prekeys_data: NewPreKeys, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    for pk in prekeys_data.prekeys:
        prekey = PreKey(user_id=user_id, public_key=pk)
        db.add(prekey)
    db.commit()
    return {"status": "ok"}

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Нет токена")
        return
    
    authenticated_user_id = verify_token(token)
    if authenticated_user_id != user_id:
        await websocket.close(code=1008, reason="Неверный токен")
        return
    
    await manager.connect(user_id, websocket)
    logger.info(f"🔌 Пользователь {user_id} подключился")
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")
            
            if msg_type == "message":
                to_user = message.get("to")
                encrypted_data = message.get("data")
                if to_user and encrypted_data:
                    await manager.send_personal_message({
                        "type": "message",
                        "from": user_id,
                        "data": encrypted_data,
                        "timestamp": datetime.now().isoformat()
                    }, to_user)
            elif msg_type in ("offer", "answer", "candidate"):
                to_user = message.get("to")
                if to_user:
                    await manager.send_personal_message({
                        "type": msg_type,
                        "from": user_id,
                        "payload": message.get("payload")
                    }, to_user)
    except WebSocketDisconnect:
        manager.disconnect(user_id)
        logger.info(f"🔌 Пользователь {user_id} отключился")
