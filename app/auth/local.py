"""Local provider. Replace this adapter, not application routes, for SSO."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from uuid import uuid4

from app.auth.contracts import Role, User
from app.services.database import Database

ITERATIONS = 310_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, raw_iterations, encoded_salt, encoded_digest = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(encoded_salt), int(raw_iterations))
        return hmac.compare_digest(candidate, base64.b64decode(encoded_digest))
    except (ValueError, TypeError):
        return False


class LocalIdentityProvider:
    def __init__(self, database: Database):
        self.database = database

    def register(self, email: str, display_name: str, password: str, role: Role) -> User:
        email = email.strip().lower()
        if self.database.find_user_by_email(email):
            raise ValueError("Ya existe una cuenta con ese correo electrónico.")
        user = User(str(uuid4()), email, display_name.strip(), role)
        self.database.create_user(user, hash_password(password))
        return user

    def authenticate(self, email: str, password: str) -> User | None:
        record = self.database.find_user_by_email(email.strip().lower())
        if not record or not verify_password(password, record["password_hash"]):
            return None
        return User(record["id"], record["email"], record["display_name"], record["role"])

    def get_user(self, user_id: str) -> User | None:
        record = self.database.find_user_by_id(user_id)
        return User(record["id"], record["email"], record["display_name"], record["role"]) if record else None
