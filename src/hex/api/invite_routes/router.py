"""Invite endpoints: owner CRUD (server-side authz) + a public, rate-limited acceptance preview.

Invites are capabilities (non-negotiable #5): single-use, expiring, ≥256-bit, revocable. The owner
surface is gated by ``require_owner`` (the owner/user boundary, non-negotiable #8); the public
preview is throttled and enumeration-resistant — any invalid/expired/revoked/spent token returns the
same 404. Acceptance (signup + provision) lands in Slices 6-2/6-3.
"""

import logging
import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from hex.api.auth_routes.dependencies import require_owner
from hex.api.guards import forbid_until_setup_complete
from hex.api.schemas import (
    InviteCreatedResponse,
    InviteCreateRequest,
    InvitePreviewResponse,
    InviteResponse,
)
from hex.database import AuditLogManager, Invite, InviteManager, User, get_session
from hex.database.models import AuditAction, AuditResult, AuditSeverity
from hex.setup import AttemptLimiter

log = logging.getLogger("hex.invite")
router = APIRouter(tags=["invites"])

_OWNER_ONLY = (Depends(forbid_until_setup_complete),)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _status(invite: Invite) -> str:
    if invite.revoked_at is not None:
        return "revoked"
    if invite.accepted_at is not None:
        return "accepted"
    if _aware(invite.expires_at) <= datetime.now(UTC):
        return "expired"
    return "active"


def _to_response(invite: Invite) -> InviteResponse:
    return InviteResponse(
        id=invite.id,
        status=_status(invite),
        requestable=invite.requestable,
        grant_providers=sorted(invite.default_grants),
        created_at=invite.created_at,
        expires_at=invite.expires_at,
        accepted_at=invite.accepted_at,
        revoked_at=invite.revoked_at,
    )


@router.post("/invites", status_code=status.HTTP_201_CREATED, dependencies=list(_OWNER_ONLY))
async def create_invite(
    body: InviteCreateRequest,
    request: Request,
    owner: Annotated[User, Depends(require_owner)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InviteCreatedResponse:
    """Create an invite; the raw token is returned exactly once. Audited as a privileged action."""
    manager = InviteManager(session)
    try:
        invite, raw = await manager.create(
            owner_id=owner.id,
            default_grants=body.default_grants,
            requestable=body.requestable,
            ttl_seconds=body.ttl_hours * 3600,
        )
        await AuditLogManager(session, request.app.state.audit_signer).append(
            action=AuditAction.INVITE_CREATED,
            severity=AuditSeverity.NOTICE,
            result=AuditResult.SUCCESS,
            actor=f"user:{owner.id}",
            target=f"invite:{invite.id}",
        )
        await session.commit()
    except SQLAlchemyError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable"
        ) from exc
    return InviteCreatedResponse(id=invite.id, token=raw, expires_at=invite.expires_at)


@router.get("/invites", dependencies=list(_OWNER_ONLY))
async def list_invites(
    owner: Annotated[User, Depends(require_owner)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[InviteResponse]:
    """Every invite with its computed status — never the token."""
    return [_to_response(invite) for invite in await InviteManager(session).list_all()]


@router.post("/invites/{invite_id}/revoke", dependencies=list(_OWNER_ONLY))
async def revoke_invite(
    invite_id: int,
    request: Request,
    owner: Annotated[User, Depends(require_owner)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InviteResponse:
    """Revoke an unaccepted invite. 409 if it is already accepted/revoked or unknown."""
    manager = InviteManager(session)
    try:
        invite = await manager.revoke(invite_id)
        if invite is None:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="invite cannot be revoked"
            )
        await AuditLogManager(session, request.app.state.audit_signer).append(
            action=AuditAction.INVITE_REVOKED,
            severity=AuditSeverity.NOTICE,
            result=AuditResult.SUCCESS,
            actor=f"user:{owner.id}",
            target=f"invite:{invite_id}",
        )
        await session.commit()
    except SQLAlchemyError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable"
        ) from exc
    return _to_response(invite)


@router.get("/invite/{token}")
async def preview_invite(
    token: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InvitePreviewResponse:
    """Public, throttled preview of what a valid invite offers. Any bad token → a uniform 404."""
    limiter: AttemptLimiter = request.app.state.invite_limiter
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    if limiter.blocked(client, now):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too many attempts"
        )
    invite = await InviteManager(session).resolve_valid(token)
    if invite is None:
        limiter.record_failure(client, now)  # only failed lookups cost budget
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return InvitePreviewResponse(
        requestable=invite.requestable,
        grant_providers=sorted(invite.default_grants),
        expires_at=invite.expires_at,
    )
