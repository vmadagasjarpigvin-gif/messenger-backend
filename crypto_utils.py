import os
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import base64

# --- Генерация ключей ---
def generate_identity_keypair():
    private_key = x25519.X25519PrivateKey.generate()
    public_key = private_key.public_key()
    return private_key, public_key

def generate_prekey():
    return generate_identity_keypair()  # prekey — тоже пара X25519

# --- ECDH + HKDF + AES-256-GCM ---
def derive_shared_secret(my_private_key, their_public_key):
    shared_secret = my_private_key.exchange(their_public_key)
    # HKDF для получения ключа шифрования
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"messenger",
        backend=default_backend()
    )
    return hkdf.derive(shared_secret)

def encrypt_message(key: bytes, plaintext: bytes) -> bytes:
    iv = os.urandom(12)
    cipher = Cipher(algorithms.AES(key), modes.GCM(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(plaintext) + encryptor.finalize()
    return iv + encryptor.tag + ciphertext

def decrypt_message(key: bytes, encrypted: bytes) -> bytes:
    iv = encrypted[:12]
    tag = encrypted[12:28]
    ciphertext = encrypted[28:]
    cipher = Cipher(algorithms.AES(key), modes.GCM(iv, tag), backend=default_backend())
    decryptor = cipher.decryptor()
    return decryptor.update(ciphertext) + decryptor.finalize()

# --- Преобразование ключей в base64 для передачи ---
def key_to_base64(key):
    return base64.b64encode(key.public_bytes_raw()).decode('ascii')

def base64_to_public_key(b64_str):
    raw = base64.b64decode(b64_str)
    return x25519.X25519PublicKey.from_public_bytes(raw)