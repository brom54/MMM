"""
MMM — Inbound Authentication
==============================
Controls who can talk TO the MMM proxy.

Auth layers (in order):
    1. IP allowlist    (MMM_ALLOWED_IPS, optional)
    2. API key         (checked against database OR env master key)

Database-backed keys:
    - Generated via POST /mmm/keys/generate
    - Stored as SHA-256 hashes in mmm.db
    - Labeled for audit attribution
    - Revocable without restart

Master key override (MMM_API_KEY in .env):
    - Works even if database is empty or unavailable
    - Used for bootstrap and emergency access
    - Never stored in database
    - Identified as "master" in audit log

IP allowlist (MMM_ALLOWED_IPS):
    - Comma-separated IPs or CIDR ranges
    - Optional — all IPs allowed if not set
    - Independent of key auth

Phase 4: adds username/password login, session tokens
Phase 5: adds OAuth2/SSO
"""

import ipaddress
import logging
import os
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from database import lookup_key, Identity

log = logging.getLogger("mmm.auth")

DEFAULT_API_KEY = "CHANGE_ME"


# ─────────────────────────────────────────────
#  REQUEST CONTEXT
#  Flows through every request.
#  Phase 1: populated by key/IP checks.
#  Phase 4: carries user_id, roles, session.
# ─────────────────────────────────────────────
class RequestContext:
    def __init__(self):
        self.authenticated:   bool            = False
        self.auth_method:     str             = "none"
        self.client_ip:       str             = ""
        self.identity:        Optional[Identity] = None

        # Convenience properties
        self.identity_id:     Optional[str]   = None
        self.identity_label:  str             = "anonymous"
        self.is_admin:        bool            = False

        # Phase 4 stubs
        self.user_id:         Optional[str]   = None
        self.username:        Optional[str]   = None
        self.roles:           list[str]       = []
        # Phase 5 stubs
        self.oauth_provider:  Optional[str]   = None
        self.oauth_token:     Optional[str]   = None

    def set_identity(self, identity: Identity):
        """Populate context from a resolved Identity record."""
        self.identity       = identity
        self.identity_id    = identity.id
        self.identity_label = identity.label
        self.is_admin       = identity.role == "admin"
        self.auth_method    = "api_key"
        self.authenticated  = True


# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
def _load_master_key() -> str:
    key = os.getenv("MMM_API_KEY", DEFAULT_API_KEY)
    if key == DEFAULT_API_KEY:
        log.warning(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "  SECURITY WARNING: MMM_API_KEY is set to 'CHANGE_ME'\n"
            "  Set MMM_API_KEY in your .env file to secure MMM.\n"
            "  Then use POST /mmm/keys/generate for additional keys.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    elif not key:
        log.warning("MMM_API_KEY is empty — master key auth DISABLED")
    return key


def _load_allowed_ips() -> list:
    raw = os.getenv("MMM_ALLOWED_IPS", "").strip()
    if not raw:
        return []
    networks = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
            log.info(f"IP allowlist: {entry}")
        except ValueError:
            log.warning(f"Invalid IP/CIDR in MMM_ALLOWED_IPS: '{entry}'")
    return networks


# ─────────────────────────────────────────────
#  AUTH MIDDLEWARE
# ─────────────────────────────────────────────
class MMMAuthMiddleware(BaseHTTPMiddleware):
    """
    Inbound authentication middleware.

    Key resolution order:
        1. Check database for matching key hash
        2. Fall back to master key (MMM_API_KEY env var)
        3. Reject if neither matches

    Both checks are bypassed if key auth is disabled (empty MMM_API_KEY).
    """

    def __init__(self, app, master_key: str, allowed_ips: list):
        super().__init__(app)
        self.master_key   = master_key
        self.allowed_ips  = allowed_ips
        self.key_enabled  = bool(master_key)

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    def _check_ip(self, client_ip: str) -> bool:
        if not self.allowed_ips:
            return True
        try:
            addr = ipaddress.ip_address(client_ip)
            return any(addr in network for network in self.allowed_ips)
        except ValueError:
            return False

    def _extract_key(self, request: Request) -> Optional[str]:
        """Extract API key from Authorization or X-API-Key header."""
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        return request.headers.get("X-API-Key") or None

    def _resolve_identity(self, plain_key: str) -> Optional[tuple]:
        """
        Resolve a key to an identity.

        Returns:
            Tuple of (Identity, auth_method) or None if invalid.
            auth_method is "db_key" or "master_key".
        """
        # 1. Check database first
        try:
            identity = lookup_key(plain_key)
            if identity:
                return identity, "db_key"
        except Exception as e:
            log.warning(f"DB key lookup failed: {e} — falling back to master key")

        # 2. Fall back to master key
        if self.master_key and plain_key == self.master_key:
            # Master key — create a synthetic Identity for context
            master_identity = Identity(
                id         = "master",
                key_hash   = "",
                label      = "master",
                type       = "user",
                created_at = "",
                role       = "admin",
            )
            return master_identity, "master_key"

        return None

    def _make_error(self, status: int, message: str) -> JSONResponse:
        return JSONResponse(
            {"error": message, "mmm": "Make Modelfiles Matter"},
            status_code=status
        )

    async def dispatch(self, request: Request, call_next):
        client_ip = self._get_client_ip(request)

        ctx = RequestContext()
        ctx.client_ip = client_ip

        # ── IP check ──────────────────────────────────────────────────
        if not self._check_ip(client_ip):
            log.warning(f"Blocked: {client_ip} not in IP allowlist")
            return self._make_error(403, f"IP address {client_ip} is not allowed")

        # ── Key check ─────────────────────────────────────────────────
        if self.key_enabled:
            plain_key = self._extract_key(request)

            if not plain_key:
                log.warning(f"Blocked: no API key from {client_ip} for {request.url.path}")
                return self._make_error(
                    401,
                    "Missing API key. Set Authorization: Bearer <key> "
                    "or X-API-Key: <key> header."
                )

            result = self._resolve_identity(plain_key)
            if not result:
                log.warning(f"Blocked: invalid API key from {client_ip}")
                return self._make_error(401, "Invalid API key.")

            identity, auth_method = result
            ctx.set_identity(identity)
            ctx.auth_method = auth_method
            log.debug(f"Auth: {identity.label} via {auth_method} from {client_ip}")
        else:
            ctx.authenticated  = True
            ctx.auth_method    = "disabled"
            ctx.identity_label = "anonymous"

        request.state.mmm_ctx = ctx
        response = await call_next(request)
        return response


# ─────────────────────────────────────────────
#  FACTORY
# ─────────────────────────────────────────────
def create_auth_middleware(app):
    """Load config and attach auth middleware to the FastAPI app."""
    master_key  = _load_master_key()
    allowed_ips = _load_allowed_ips()
    app.add_middleware(
        MMMAuthMiddleware,
        master_key  = master_key,
        allowed_ips = allowed_ips
    )
    log.info(f"Auth: key={'enabled' if master_key else 'disabled'} "
             f"IP allowlist={'enabled' if allowed_ips else 'disabled'}")
    return app
