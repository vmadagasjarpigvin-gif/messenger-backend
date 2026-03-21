from pydantic import BaseModel, Field
from typing import List, Optional

class InviteCodeCheck(BaseModel):
    code: str

class UserRegister(BaseModel):
    username: str
    invite_code: str
    identity_public_key: str          # base64 encoded
    prekeys: List[str] = Field(..., min_items=1, max_items=100)   # список prekey public keys

class UserResponse(BaseModel):
    id: int
    username: str
    identity_public_key: str

class PreKeyBundle(BaseModel):
    user_id: int
    identity_public_key: str
    prekey_public_key: str

class NewPreKeys(BaseModel):
    prekeys: List[str]

class Token(BaseModel):
    access_token: str
    token_type: str