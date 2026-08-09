from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from app.auth.contracts import IdentityProvider, Role, User
from app.services.database import Database


class AuthService:
    def __init__(self, provider: IdentityProvider, database: Database, session_days: int):
        self.provider, self.database, self.session_days = provider, database, session_days

    def register(self, email: str, display_name: str, password: str, role: Role) -> User:
        if len(password) < 10:
            raise ValueError("La contraseña debe tener al menos 10 caracteres.")
        if not display_name.strip():
            raise ValueError("Indica tu nombre.")
        return self.provider.register(email, display_name, password, role)

    def login(self, email: str, password: str) -> tuple[User, str] | None:
        user = self.provider.authenticate(email, password)
        if not user:
            return None
        token = secrets.token_urlsafe(32)
        self.database.create_session(self._token_hash(token), user.id, datetime.now(UTC) + timedelta(days=self.session_days))
        return user, token

    def current_user(self, token: str | None) -> User | None:
        if not token:
            return None
        user_id = self.database.user_id_for_session(self._token_hash(token), datetime.now(UTC))
        return self.provider.get_user(user_id) if user_id else None

    def logout(self, token: str | None) -> None:
        if token:
            self.database.delete_session(self._token_hash(token))

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
