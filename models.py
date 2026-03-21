from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    identity_public_key = Column(Text, nullable=False)  # X25519 public key (base64)
    invite_code_used = Column(String, nullable=False)   # какой код использован
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    prekeys = relationship("PreKey", back_populates="user", cascade="all, delete-orphan")

class PreKey(Base):
    __tablename__ = "prekeys"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    public_key = Column(Text, nullable=False)   # X25519 public key (base64)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="prekeys")

class InviteCode(Base):
    __tablename__ = "invite_codes"
    code = Column(String, primary_key=True, index=True)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())