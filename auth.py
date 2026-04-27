"""
MMM - Inbound Authentication
==============================
Controls who can talk TO the MMM proxy.

Features:
    - Static API key  (MMM_API_KEY, default: CHANGE_ME)
    - IP allowlist    (MMM_ALLOWED_IPS, optional)

Both are optional and independent.

Configuration via .env file:
    MMM_API_KEY=your-secret-key-here
    MMM_ALLOWED_IPS=192.168.1.0/24,10.0.0.5

Phase 4: Local user accounts, per-user keys (database.py)
Phase 5: OAuth2/SSO
"""

import ipaddress
import logging
import os
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

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
        self.authenticated:  bool          = False
        self.auth_method:    str           = "none"
        self.client_ip:      str           = ""
        self.identity_label: str           = "anonymous"
        self.is_admin:       bool          = False

        # Phase 4 stubs
        self.user_id:        Optional[str] = None
        self.username:       Optional[str] = None
        self.roles:          list[str]     = []
        # Phase 5 stubs
        self.oauth_provider: Optional[str] = None
        self.oauth_token:    Optional[str] = None


# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
def _load_master_key() -> str:
    key = os.getenv("MMM_API_KEY", DEFAULT_API_KEY)
    if key == DEFAULT_API_KEY:
        log.warning(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "  SECURITY WARNING: MMM_API_KEY is set to 'CHANGE_ME'\n"
            "  Anyone who can reach this port can use MMM.\n"
            "  Set MMM_API_KEY in your .env file to secure it.\n"
            "  See README for instructions.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
    elif not key:
        log.warning("MMM_API_KEY is empty - API key authentication is DISABLED.")
    else:
        log.info("API key authentication: enabled")
    return key


def _load_allowed_ips() -> list:
    raw = os.getenv("MMM_ALLOWED_IPS", "").strip()
    if not raw:
        log.info("IP allowlist: disabled (all IPs allowed)")
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
            log.warning(f"Invalid IP/CIDR in MMM_ALLOWED_IPS: '{entry}' - skipping")
    return networks


# ─────────────────────────────────────────────
#  AUTH MIDDLEWARE
# ─────────────────────────────────────────────
class MMMAuthMiddleware(BaseHTTPMiddleware):
    """
    Inbound authentication middleware.

    Checks:
        1. IP allowlist (if configured)
        2. API key (if MMM_API_KEY is set and not empty)

    Both checks are independent and individually optional.
    Phase 4 will add database-backed per-user key lookup here.
    """

    def __init__(self, app, master_key: str, allowed_ips: list):
        super().__init__(app)
        self.master_key  = master_key
        self.allowed_ips = allowed_ips
        self.key_enabled = bool(master_key)

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
            log.warning(f"Could not parse client IP: {client_ip}")
            return False

    def _check_key(self, request: Request) -> bool:
        if not self.key_enabled:
            return True
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:] == self.master_key
        x_api_key = request.headers.get("X-API-Key", "")
        if x_api_key:
            return x_api_key == self.master_key
        return False

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
            if not self._check_key(request):
                log.warning(f"Blocked: invalid/missing API key from {client_ip}")
                return self._make_error(
                    401,
                    "Invalid or missing API key. "
                    "Set Authorization: Bearer <key> or X-API-Key: <key> header. "
                    "Configure your key with MMM_API_KEY in .env"
                )
            ctx.identity_label = "master"
            ctx.is_admin       = True

        ctx.authenticated = True
        ctx.auth_method   = "api_key" if self.key_enabled else "disabled"

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
    return app
