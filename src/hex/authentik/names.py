"""Canonical names of the objects deploy/authentik/blueprints/hex.yaml creates.

Single source for the verify diagnostic and the bootstrap orchestrator so they can't drift.
"""

PROVIDER_NAME = "HEx web BFF"
SA_USERNAME = "hex-provisioner"
GROUP_NAME = "HEx Provisioners"
# Identifier of the scoped API token HEx mints for itself and rotates the bootstrap token onto.
SA_TOKEN_IDENTIFIER = "hex-provisioner-token"  # noqa: S105 — an identifier, not a credential
