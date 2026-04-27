"""
MMM — Secrets Provider
=======================
Manages outbound API keys for cloud providers.

Phase 1: Environment variable backed (via .env file).
Phase 2.5: Will add keyring and encrypted file backing.

Usage:
    from secrets_provider import secrets
    key = secrets.get_api_key("openai")

Never log or print API keys. The provider logs key presence only.
"""

import logging
import os
from typing import Optional

log = logging.getLogger("mmm.secrets")

# ─────────────────────────────────────────────
#  PROVIDER KEY NAMES
#  Maps provider name → environment variable
# ─────────────────────────────────────────────
PROVIDER_ENV_VARS = {
    "openai":    "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "groq":      "GROQ_API_KEY",
    "mistral":   "MISTRAL_API_KEY",
    "cohere":    "COHERE_API_KEY",
    # Phase 2.5: add more providers here
}


class SecretsProvider:
    """
    Abstraction layer for API key storage and retrieval.

    Current backing: environment variables / .env file
    Future backing:  OS keychain (keyring library), encrypted file

    The interface is stable — callers don't need to change when
    the backing store changes in Phase 2.5.
    """

    def __init__(self):
        self._backend = "env"
        # Phase 2.5: detect and use keyring if available
        # Phase 2.5: detect and use encrypted file if configured
        log.info(f"Secrets provider: {self._backend}")
        self._log_available_keys()

    def _log_available_keys(self):
        """Log which provider keys are configured (never log the values)."""
        available = [
            provider for provider, env_var in PROVIDER_ENV_VARS.items()
            if os.getenv(env_var)
        ]
        if available:
            log.info(f"API keys configured for: {', '.join(available)}")
        else:
            log.debug("No cloud provider API keys configured")

    def get_api_key(self, provider: str) -> Optional[str]:
        """
        Get the API key for a cloud provider.

        Args:
            provider: Provider name (e.g. 'openai', 'anthropic')

        Returns:
            API key string, or None if not configured
        """
        env_var = PROVIDER_ENV_VARS.get(provider.lower())
        if not env_var:
            log.warning(f"Unknown provider '{provider}' — no key lookup defined")
            return None

        key = os.getenv(env_var)
        if key:
            log.debug(f"API key found for '{provider}'")
        else:
            log.debug(f"No API key configured for '{provider}' ({env_var} not set)")
        return key

    def has_api_key(self, provider: str) -> bool:
        """Check if an API key is configured for a provider."""
        return self.get_api_key(provider) is not None

    def get_auth_header(self, provider: str) -> Optional[dict]:
        """
        Get the appropriate Authorization header for a provider.

        Different providers use different auth header formats:
            OpenAI, Groq, Mistral: Authorization: Bearer <key>
            Anthropic:             x-api-key: <key>

        Returns:
            Dict with header name/value, or None if no key configured
        """
        key = self.get_api_key(provider)
        if not key:
            return None

        # Anthropic uses a different header
        if provider.lower() == "anthropic":
            return {"x-api-key": key, "anthropic-version": "2023-06-01"}

        # Standard bearer token for everyone else
        return {"Authorization": f"Bearer {key}"}

    # ── Phase 2.5 stubs ────────────────────────────────────────────────────

    def set_api_key(self, provider: str, key: str) -> bool:
        """
        Store an API key. Phase 1: not implemented (use .env file).
        Phase 2.5: will write to keyring or encrypted file.
        """
        log.warning(
            f"set_api_key not yet implemented. "
            f"Set {PROVIDER_ENV_VARS.get(provider, provider.upper() + '_API_KEY')} "
            f"in your .env file instead."
        )
        return False

    def delete_api_key(self, provider: str) -> bool:
        """
        Delete a stored API key. Phase 2.5 feature.
        """
        log.warning("delete_api_key not yet implemented.")
        return False


# Singleton instance
secrets = SecretsProvider()
