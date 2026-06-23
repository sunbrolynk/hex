"""wire_authentik: the full bootstrap wiring — persist-encrypted-and-audit, and fail-secure."""

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hex.audit import AuditSigner
from hex.authentik import (
    AuthentikUnreachable,
    OverprivilegedServiceAccount,
    WiringFailed,
    wire_authentik,
)
from hex.authentik.names import SA_TOKEN_IDENTIFIER
from hex.config import Settings
from hex.database import AuthentikIntegrationManager
from hex.database.models import AuditAction, AuditLogEntry
from hex.secrets import broker_from_settings
from tests.conftest import make_settings

_BASE = "http://ak.test"
_API = f"{_BASE}/api/v3"


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "authentik_base_url": _BASE,
        "authentik_bootstrap_token": "bootstrap-token",
    }
    return make_settings(**(base | overrides))


def _mock_authentik(
    *, sa_superuser: bool = False, secret: str = "prov-secret", key: str = "sa-key"
) -> None:
    """Mock the full happy Authentik surface the orchestrator touches. Call inside respx.mock."""
    respx.get(f"{_BASE}/-/health/ready/").mock(return_value=httpx.Response(204))
    respx.get(f"{_API}/core/applications/").mock(
        return_value=httpx.Response(200, json={"results": [{"slug": "hex", "name": "HEx"}]})
    )
    respx.get(f"{_API}/providers/oauth2/").mock(
        return_value=httpx.Response(
            200, json={"results": [{"pk": 7, "name": "HEx web BFF", "client_id": "cid"}]}
        )
    )
    respx.get(f"{_API}/core/groups/").mock(
        return_value=httpx.Response(200, json={"results": [{"pk": 3, "name": "HEx Provisioners"}]})
    )
    respx.get(f"{_API}/core/users/").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [{"pk": 11, "username": "hex-provisioner", "is_superuser": sa_superuser}]
            },
        )
    )
    respx.get(f"{_API}/providers/oauth2/7/").mock(
        return_value=httpx.Response(200, json={"client_secret": secret})
    )
    respx.post(f"{_API}/core/tokens/").mock(return_value=httpx.Response(201, json={}))
    respx.get(f"{_API}/core/tokens/{SA_TOKEN_IDENTIFIER}/view_key/").mock(
        return_value=httpx.Response(200, json={"key": key})
    )


async def _audit_actions(session: AsyncSession) -> list[AuditAction]:
    rows = (await session.execute(select(AuditLogEntry).order_by(AuditLogEntry.id))).scalars().all()
    return [r.action for r in rows]


async def test_wire_persists_encrypted_secrets_and_audits(db_session: AsyncSession) -> None:
    settings = _settings()
    broker = broker_from_settings(settings)
    signer = AuditSigner.from_settings(settings)
    with respx.mock:
        _mock_authentik(secret="prov-secret", key="sa-key")
        async with httpx.AsyncClient() as http:
            result = await wire_authentik(
                settings=settings,
                http=http,
                broker=broker,
                session=db_session,
                audit_signer=signer,
            )
    assert result.client_id == "cid"
    assert result.provider_pk == 7

    row = await AuthentikIntegrationManager(db_session).get()
    assert row is not None
    assert row.client_id == "cid"
    assert row.provider_pk == 7
    assert row.wired_at is not None
    # Secrets are stored encrypted and decrypt back to the originals — never plaintext at rest.
    assert row.client_secret_enc is not None and row.client_secret_enc != "prov-secret"
    assert row.sa_token_enc is not None
    assert broker.decrypt(row.client_secret_enc).decode() == "prov-secret"
    assert broker.decrypt(row.sa_token_enc).decode() == "sa-key"
    # Both privileged steps are HIGH-severity audit events.
    actions = await _audit_actions(db_session)
    assert AuditAction.AUTHENTIK_WIRING_SUCCEEDED in actions
    assert AuditAction.BOOTSTRAP_TOKEN_ROTATED in actions


async def test_wire_without_bootstrap_token_persists_nothing(db_session: AsyncSession) -> None:
    settings = make_settings(authentik_base_url=_BASE)  # no bootstrap token
    broker = broker_from_settings(settings)
    signer = AuditSigner.from_settings(settings)
    async with httpx.AsyncClient() as http:
        with pytest.raises(WiringFailed):
            await wire_authentik(
                settings=settings, http=http, broker=broker, session=db_session, audit_signer=signer
            )
    assert await AuthentikIntegrationManager(db_session).get() is None


async def test_wire_without_base_url_persists_nothing(db_session: AsyncSession) -> None:
    settings = make_settings(authentik_bootstrap_token="tok")  # token set, no base URL
    broker = broker_from_settings(settings)
    signer = AuditSigner.from_settings(settings)
    async with httpx.AsyncClient() as http:
        with pytest.raises(WiringFailed):
            await wire_authentik(
                settings=settings, http=http, broker=broker, session=db_session, audit_signer=signer
            )
    assert await AuthentikIntegrationManager(db_session).get() is None


async def test_wire_refuses_superuser_sa_and_persists_nothing(db_session: AsyncSession) -> None:
    settings = _settings()
    broker = broker_from_settings(settings)
    signer = AuditSigner.from_settings(settings)
    with respx.mock:
        _mock_authentik(sa_superuser=True)
        # The secret read-back + token mint must never run for an over-privileged SA.
        secret_route = respx.get(f"{_API}/providers/oauth2/7/")
        token_route = respx.post(f"{_API}/core/tokens/")
        async with httpx.AsyncClient() as http:
            with pytest.raises(OverprivilegedServiceAccount):
                await wire_authentik(
                    settings=settings,
                    http=http,
                    broker=broker,
                    session=db_session,
                    audit_signer=signer,
                )
        assert not secret_route.called
        assert not token_route.called
    # Fail-secure (#3): nothing persisted, no success audit.
    assert await AuthentikIntegrationManager(db_session).get() is None
    assert AuditAction.AUTHENTIK_WIRING_SUCCEEDED not in await _audit_actions(db_session)


async def test_wire_unreachable_authentik_persists_nothing(db_session: AsyncSession) -> None:
    settings = _settings()
    broker = broker_from_settings(settings)
    signer = AuditSigner.from_settings(settings)
    with respx.mock:
        # Healthy, but the first object read fails — exercises the unreachable path fast.
        respx.get(f"{_BASE}/-/health/ready/").mock(return_value=httpx.Response(204))
        respx.get(f"{_API}/core/applications/").mock(return_value=httpx.Response(503))
        async with httpx.AsyncClient() as http:
            with pytest.raises(AuthentikUnreachable):
                await wire_authentik(
                    settings=settings,
                    http=http,
                    broker=broker,
                    session=db_session,
                    audit_signer=signer,
                )
    assert await AuthentikIntegrationManager(db_session).get() is None
