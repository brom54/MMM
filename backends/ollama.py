"""
MMM — Ollama Backend
====================
Fully implemented. This is the reference implementation — all other
backends translate to/from this format.

Ollama API docs: https://github.com/ollama/ollama/blob/main/docs/api.md
"""

import json
import logging

from .base import BaseBackend

log = logging.getLogger("mmm.backend.ollama")


class OllamaBackend(BaseBackend):

    # ── Identity ───────────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def display_name(self) -> str:
        return "Ollama"

    @property
    def default_port(self) -> int:
        return 11434

    # ── Capabilities ───────────────────────────────────────────────────────

    @property
    def supports_thinking(self) -> bool:
        return True  # Ollama supports think=true/false for compatible models

    @property
    def openai_compatible(self) -> bool:
        return False  # Ollama has its own API (also has /v1 OpenAI compat layer)

    # ── Health check ───────────────────────────────────────────────────────

    async def is_available(self, host: str, client) -> bool:
        try:
            resp = await client.get(f"{host}/api/version", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False

    # ── Model listing ──────────────────────────────────────────────────────

    async def list_models(self, host: str, client) -> list[str]:
        try:
            resp = await client.get(f"{host}/api/tags")
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            log.warning(f"Could not list Ollama models: {e}")
            return []

    # ── Request translation ────────────────────────────────────────────────

    def translate_request(self, body: dict, path: str) -> tuple[dict, str]:
        # Ollama is the native format — no translation needed
        return body, path

    # ── Response translation ───────────────────────────────────────────────

    def translate_response_chunk(self, chunk: bytes) -> bytes:
        # Strip thinking field from streaming chunks
        try:
            data = json.loads(chunk)
            data.pop("thinking", None)
            if "message" in data and isinstance(data["message"], dict):
                data["message"].pop("thinking", None)
            return json.dumps(data).encode() + b"\n"
        except Exception:
            return chunk

    def translate_response_full(self, body: bytes) -> bytes:
        # Strip thinking field from complete response
        try:
            data = json.loads(body)
            data.pop("thinking", None)
            if "message" in data and isinstance(data["message"], dict):
                data["message"].pop("thinking", None)
            return json.dumps(data).encode()
        except Exception:
            return body

    # ── Thinking mode ──────────────────────────────────────────────────────

    def apply_thinking(self, body: dict, think: bool) -> dict:
        body["think"] = think
        return body

    # ── Parameter mapping ──────────────────────────────────────────────────

    def map_parameters(self, params: dict) -> dict:
        # Ollama uses its own parameter names inside an "options" dict
        # No mapping needed — these are already Ollama format
        return params
