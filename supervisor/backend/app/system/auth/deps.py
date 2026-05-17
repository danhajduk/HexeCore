from __future__ import annotations

from fastapi import Header, HTTPException

from .tokens import (
    ServiceTokenClaims,
    ServiceTokenError,
    ServiceTokenKeyStore,
    validate_claims,
    verify_hs256,
)


def require_service_token(
    key_store: ServiceTokenKeyStore,
    audience: str,
    scopes: list[str] | None = None,
):
    async def _dep(authorization: str | None = Header(default=None)) -> ServiceTokenClaims:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="service_token_missing")
        token = authorization.split(" ", 1)[1].strip()
        keys = await key_store.all_keys()
        try:
            _, payload = verify_hs256(token, keys)
            return validate_claims(payload, audience=audience, required_scopes=scopes)
        except ServiceTokenError as e:
            raise HTTPException(status_code=401, detail=str(e))

    return _dep
