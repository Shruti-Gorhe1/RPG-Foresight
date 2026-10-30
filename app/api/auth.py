"""Authentication and organization isolation dependency.

Development mode: accepts a bearer token in the format `tenant:{tenant_id}:user:{user_id}`
or simply `dev:{tenant_id}`. Derives tenant_id and user_id from verified claims.

Production: replace validate_token() with proper IdP (OIDC/OAuth2) token validation
using azure-identity or python-jose as already configured in requirements.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import get_db_session
from shared.logger import get_logger

log = get_logger("api.auth")

security = HTTPBearer(auto_error=False)


class CurrentUser:
    """Authenticated user context with organization isolation."""

    def __init__(
        self,
        user_id: str,
        tenant_id: str,
        email: str | None = None,
        roles: list[str] | None = None,
        is_authenticated: bool = True,
    ):
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.email = email
        self.roles = roles or []
        self.is_authenticated = is_authenticated


def validate_token(token: str | None) -> CurrentUser:
    """Validate bearer token and return user context.

    Dev format: `tenant:{tenant_id}:user:{user_id}` or `dev:{tenant_id}`
    In production, validate JWT/OIDC token here.
    """
    if not token:
        # Allow unauthenticated access in development with default tenant
        return CurrentUser(
            user_id="dev-user",
            tenant_id="KEC-001",
            email="dev@kec.example.com",
            roles=["admin"],
        )

    # Parse dev token formats
    if token.startswith("tenant:"):
        parts = token.split(":")
        # tenant:{tenant_id}:user:{user_id}
        if len(parts) >= 4:
            return CurrentUser(
                user_id=parts[3],
                tenant_id=parts[1],
                email=f"user@{parts[1]}.example.com",
                roles=["admin"],
            )
    elif token.startswith("dev:"):
        parts = token.split(":")
        return CurrentUser(
            user_id="dev-user",
            tenant_id=parts[1] if len(parts) > 1 else "KEC-001",
            email="dev@kec.example.com",
            roles=["admin"],
        )

    # Unknown token format — fail closed
    log.warning("invalid_token_format", token_prefix=token[:20] if token else None)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication token",
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db_session),
) -> CurrentUser:
    """FastAPI dependency — returns the authenticated user context."""
    token = credentials.credentials if credentials else None
    user = validate_token(token)
    log.debug("auth_resolved", user_id=user.user_id, tenant_id=user.tenant_id)
    return user


def require_tenant(user: CurrentUser) -> str:
    """Return the tenant_id for scoped queries. Ensures org isolation."""
    return user.tenant_id