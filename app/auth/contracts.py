from dataclasses import dataclass
from typing import Literal, Protocol

Role = Literal["student", "tutor"]


@dataclass(frozen=True)
class User:
    id: str
    email: str
    display_name: str
    role: Role


class IdentityProvider(Protocol):
    """Contract an OIDC/SAML provider can implement in the future."""
    def register(self, email: str, display_name: str, password: str, role: Role) -> User: ...
    def authenticate(self, email: str, password: str) -> User | None: ...
    def get_user(self, user_id: str) -> User | None: ...
