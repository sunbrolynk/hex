"""Invite endpoints: owner CRUD (server-side authz) + a public, rate-limited acceptance preview.

Invites are capabilities (non-negotiable #5): single-use, expiring, ≥256-bit, revocable. The owner
surface is gated by ``require_owner`` (the owner/user boundary, non-negotiable #8); the public
preview is throttled and enumeration-resistant — any invalid/expired/revoked/spent token returns the
same 404. Acceptance (signup + provision) lands in Slices 6-2/6-3.
"""

import logging
import time
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from hex.api.auth_routes.dependencies import require_owner
from hex.api.guards import forbid_until_setup_complete
from hex.api.schemas import (
    InviteAcceptResponse,
    InviteCreatedResponse,
    InviteCreateRequest,
    InviteListResponse,
    InvitePreviewResponse,
    InviteResponse,
)
from hex.authentik.errors import AuthentikError
from hex.authentik.management_client import AuthentikManagementClient
from hex.authentik.runtime_config import resolve_sa_credentials
from hex.database import (
    AuditLogManager,
    AuthentikIntegrationManager,
    Invite,
    InviteManager,
    User,
    get_session,
)
from hex.database.models import AuditAction, AuditResult, AuditSeverity
from hex.providers import ProviderRegistry
from hex.secrets.errors import InvalidToken
from hex.setup import AttemptLimiter, hash_token, mint_token

log = logging.getLogger("hex.invite")
router = APIRouter(tags=["invites"])

# httponly cookie carrying a server-minted nonce (matched to invites.accept_nonce_hash) through the
# Authentik enrollment trip. Slice 6-2c reads it at the OIDC callback to find the invite, set
# accepted_by + provision. Read by auth_routes. NOT the raw invite token (which is already burned).
INVITE_COOKIE = "hex_invite"  # noqa: S105 — cookie name, not a credential

_OWNER_ONLY = (Depends(forbid_until_setup_complete),)


def _reject_unknown() -> HTTPException:
    # Uniform, non-leaky: don't distinguish unknown-provider from unknown-tier.
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="unknown provider or tier"
    )


def _resolve_grants(registry: ProviderRegistry, default_grants: dict[str, str]) -> dict[str, Any]:
    """Resolve owner-picked ``{provider_id: tier_key}`` to ``{provider_id: structured grant}``.

    Every provider id AND tier key is validated against the registry; the server holds the grant a
    key resolves to, so no owner-authored grant blob is trusted. Any miss → 422 (ADR 0015).
    """
    resolved: dict[str, Any] = {}
    for provider_id, tier_key in default_grants.items():
        provider = registry.get(provider_id)
        template = (
            next((t for t in provider.available_grants() if t.key == tier_key), None)
            if provider is not None
            else None
        )
        if provider is None or template is None:
            raise _reject_unknown()
        # Re-validate the provider-authored tier through its grant model, so the stored grant is
        # guaranteed to satisfy the structured-grant contract 6-3 provisioning reads back.
        resolved[provider_id] = provider.parse_grant(template.grant).model_dump()
    return resolved


def _validate_requestable(registry: ProviderRegistry, requestable: list[str]) -> None:
    """Every requestable provider id must exist in the registry (no phantom/unknown services)."""
    for provider_id in requestable:
        if registry.get(provider_id) is None:
            raise _reject_unknown()


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
        recipient=invite.recipient,
        recipient_kind=invite.recipient_kind,
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
    """Create an invite; the raw token is returned exactly once. Audited as a privileged action.

    Grants + requestable are validated against the provider registry BEFORE anything is stored: the
    owner-picked tier keys resolve to structured grants, and unknown providers/tiers are rejected
    (422) — an invite can never carry a grant for a service/tier that doesn't exist (ADR 0015).
    """
    registry: ProviderRegistry = request.app.state.registry
    resolved_grants = _resolve_grants(registry, body.default_grants)
    _validate_requestable(registry, body.requestable)
    manager = InviteManager(session)
    try:
        invite, raw = await manager.create(
            owner_id=owner.id,
            default_grants=resolved_grants,
            requestable=body.requestable,
            ttl_seconds=body.ttl_hours * 3600,
            recipient=body.recipient,
            recipient_kind=body.recipient_kind,
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
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InviteListResponse:
    """A page of invites (newest first) with computed status + total — never the token."""
    manager = InviteManager(session)
    items = [_to_response(invite) for invite in await manager.list_page(limit=limit, offset=offset)]
    return InviteListResponse(items=items, total=await manager.count(), limit=limit, offset=offset)


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


@router.get("/invite/{token}/preview")
async def preview_invite(
    token: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InvitePreviewResponse:
    """Public, throttled preview of what a valid invite offers. Any bad token → a uniform 404.

    Lives at ``/preview`` so the bare ``/invite/{token}`` path is free for the SPA acceptance page.
    """
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


@router.post("/invite/{token}/accept")
async def accept_invite(
    token: str,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InviteAcceptResponse:
    """Consume the invite (single-use) and mint an Authentik enrollment invitation to redirect to.

    Atomic + fail-secure: the HEx invite is burned only if a matching Authentik invitation is
    successfully minted — if minting (or the audit/commit) fails, the burn is rolled back so the
    invite is not wasted. A bad/expired/spent token returns a uniform 404.
    """
    app = request.app
    settings = app.state.settings
    limiter: AttemptLimiter = app.state.invite_limiter
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    if limiter.blocked(client, now):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too many attempts"
        )

    invite = await InviteManager(session).accept(token)  # atomic burn (uncommitted)
    if invite is None:
        await session.rollback()
        limiter.record_failure(client, now)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")

    integration = await AuthentikIntegrationManager(session).get()
    try:
        sa = resolve_sa_credentials(settings, integration, app.state.secrets)
    except InvalidToken:
        sa = None  # undecryptable SA token → fail-secure "not configured"
    if sa is None:
        await session.rollback()  # don't spend the invite when enrollment can't proceed
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="enrollment unavailable"
        )

    # A fresh server-minted nonce (NOT the burned invite token) is the enrollment-trip linkage:
    # ≥256-bit, hashed at rest on the invite (``accept_nonce_hash``). The SAME nonce travels two
    # ways — the httponly cookie (fallback) and Authentik ``fixed_data.attributes`` → the new user's
    # attribute → a SIGNED ID-token claim (primary, 6-2d). The OIDC callback matches either against
    # ``accept_nonce_hash``. An unguessable nonce (never the sequential invite id) is what makes the
    # bind a capability: a guessed/forged value can't hijack provisioning (SECURITY_MODEL §6).
    nonce = mint_token()
    invite.accept_nonce_hash = hash_token(nonce)

    client_api = AuthentikManagementClient(sa.api_base, sa.token, app.state.http)
    try:
        itoken = await client_api.create_invitation(
            name=f"hex-invite-{invite.id}",
            flow_slug=settings.enrollment_flow_slug,
            # Nest under ``attributes`` so the enrollment user-write stage PERSISTS the nonce on the
            # new user (a flat key is discarded — 6-2d spike); it returns as a signed claim.
            fixed_data={"attributes": {"hex_invite_nonce": nonce}},
            ttl_seconds=settings.enrollment_invitation_ttl_seconds,
        )
    except AuthentikError:
        await session.rollback()  # Authentik mint failed → roll back the burn (invite not spent)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="enrollment unavailable"
        ) from None

    # If the commit below fails the burn rolls back (invite reusable), but the Authentik invitation
    # just minted is orphaned. It's single-use + short-TTL, so it self-expires unused — a benign,
    # bounded artifact, and the HEx hard-cap-of-1 still holds.
    try:
        await AuditLogManager(session, app.state.audit_signer).append(
            action=AuditAction.INVITE_ACCEPTED,
            severity=AuditSeverity.NOTICE,
            result=AuditResult.SUCCESS,
            actor=f"client:{client}",
            target=f"invite:{invite.id}",
        )
        await session.commit()
    except SQLAlchemyError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database unavailable"
        ) from exc

    response.set_cookie(
        INVITE_COOKIE,
        nonce,
        max_age=settings.enrollment_invitation_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    enroll_url = (
        f"{sa.browser_base.rstrip('/')}/if/flow/{settings.enrollment_flow_slug}/?itoken={itoken}"
    )
    return InviteAcceptResponse(enroll_url=enroll_url)
