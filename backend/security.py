"""Autenticação JWT (HS256) e armazenamento privado de documentos com URLs assinadas."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from functools import wraps
from pathlib import Path

from flask import current_app, g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

JWT_TTL_SECONDS = 8 * 3600
SIGNED_URL_TTL_SECONDS = 300
ALLOWED_MIME = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


# --- JWT ------------------------------------------------------------------
def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def create_jwt(payload, secret, ttl=JWT_TTL_SECONDS):
    now = int(time.time())
    body = {**payload, "iat": now, "exp": now + ttl}
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claims = _b64(json.dumps(body, separators=(",", ":")).encode())
    signature = hmac.new(secret.encode(), f"{header}.{claims}".encode(), hashlib.sha256).digest()
    return f"{header}.{claims}.{_b64(signature)}"


def decode_jwt(token, secret):
    try:
        header, claims, signature = token.split(".")
        expected = hmac.new(secret.encode(), f"{header}.{claims}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(signature)):
            return None
        if json.loads(_unb64(header)).get("alg") != "HS256":
            return None
        body = json.loads(_unb64(claims))
    except (ValueError, json.JSONDecodeError):
        return None
    if body.get("exp", 0) < time.time():
        return None
    return body


def auth_required(role=None):
    """Exige `Authorization: Bearer <jwt>`; opcionalmente restringe por perfil ('hub' | 'driver')."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            auth = request.headers.get("Authorization", "")
            token = auth[7:] if auth.startswith("Bearer ") else None
            claims = decode_jwt(token, current_app.config["SECRET_KEY"]) if token else None
            if not claims:
                return jsonify(error="Sessão inválida ou expirada. Faça login novamente."), 401
            if role and claims.get("role") != role:
                return jsonify(error="Acesso não permitido para este perfil."), 403
            g.user_id = int(claims["sub"])
            g.role = claims["role"]
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# --- Storage privado + URLs assinadas -------------------------------------
# No MVP os arquivos ficam em disco, fora da pasta pública. Em produção, troque save_private_file /
# open_private_file por S3 (put_object + generate_presigned_url) ou Firebase Storage (signed URLs).
def _storage_dir():
    path = Path(current_app.config["STORAGE_DIR"])
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_private_file(file_storage):
    mime = file_storage.mimetype
    if mime not in ALLOWED_MIME:
        raise ValueError("Formato não suportado. Envie JPG, PNG, WEBP ou PDF.")
    data = file_storage.read()
    if not data:
        raise ValueError("Arquivo vazio.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Arquivo excede 5 MB.")
    key = secrets.token_hex(16) + ALLOWED_MIME[mime]
    (_storage_dir() / key).write_bytes(data)
    return key, mime


def private_file_path(key):
    path = (_storage_dir() / os.path.basename(key)).resolve()
    return path if path.is_file() else None


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="wayhub-docs")


def sign_storage_key(key):
    return _serializer().dumps(key)


def unsign_storage_key(token):
    try:
        return _serializer().loads(token, max_age=SIGNED_URL_TTL_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
