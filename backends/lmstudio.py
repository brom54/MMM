"""
MMM — LM Studio Backend
========================
Status: STUB — architecture in place, implementation pending.

LM Studio exposes an OpenAI-compatible local server at port 1234.
It also has a newer LM Studio API at /api/v0/ with richer model management.

API docs: https://lmstudio.ai/docs/api

Key differences from Ollama:
  - OpenAI-compatible /v1/chat/completions (primary interface)
  - LM Studio native API at /api/v0/ for model management
  - Model must be loaded in LM Studio UI or via API before use
  - Supports multiple simultaneously loaded models
  - No native thinking mode
  - TTL-based model unloading

Implementation notes for Phase 2:
  - translate_request:  Convert Ollama body to OpenAI format
  - translate_response: Convert OpenAI response to Ollama format
  - is_available:       GET /v1/models returns model list if server is running
  - list_models:        GET /v1/models

Parameter mapping (Ollama → LM Studio/OpenAI):
  temperature    → temperature          (same)
  top_p          → top_p               (same)
  top_k          → (not in OpenAI spec, passed as extra_body)
  repeat_penalty → frequency_penalty   (approximate equivalent)
  num_ctx        → (set at model load time, not per-request)
  num_predict    → max_tokens          (different name)

To use LM Studio with MMM today (pass-through mode):
  1. Enable LM Studio local server (port 1234 by default)
  2. Set in .env:
       BACKEND=lmstudio
       OLLAMA_HOST=http://localhost:1234
  3. Start MMM — character injection will work for system prompts
     Parameter injection requires Phase 2 implementation
"""

import logging
from .base import BaseBackend

log = logging.getLogger("mmm.backend.lmstudio")

NOT_IMPLEMENTED_MSG = (
    "LM Studio full parameter translation is not yet implemented. "
    "System prompt injection works in pass-through mode. "
    "See backends/lmstudio.py for implementation notes. "
    "Contributions welcome: https://github.com/yourusername/MMM"
)


class LMStudioBackend(BaseBackend):

    @property
    def name(self) -> str:
        return "lmstudio"

    @property
    def display_name(self) -> str:
        return "LM Studio"

    @property
    def default_port(self) -> int:
        return 1234

    @property
    def openai_compatible(self) -> bool:
        return True

    async def is_available(self, host: str, client) -> bool:
        try:
            resp = await client.get(f"{host}/v1/models", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self, host: str, client) -> list[str]:
        try:
            resp = await client.get(f"{host}/v1/models")
            data = resp.json()
            return [m["id"] for m in data.get("data", [])]
        except Exception:
            return []

    def translate_request(self, body: dict, path: str) -> tuple[dict, str]:
        """
        Partial implementation — passes through as-is for now.
        LM Studio accepts Ollama-format requests on /v1/chat/completions
        with some tolerance, but full translation improves compatibility.
        Full implementation in Phase 2.
        """
        # For now pass through — LM Studio's OpenAI compat layer
        # handles most Ollama-format requests reasonably well
        return body, path

    def translate_response_chunk(self, chunk: bytes) -> bytes:
        """Pass-through — Phase 2 will add proper OpenAI→Ollama translation."""
        return chunk

    def translate_response_full(self, body: bytes) -> bytes:
        """Pass-through — Phase 2 will add proper OpenAI→Ollama translation."""
        return body

    def map_parameters(self, params: dict) -> dict:
        mapping = {
            "num_predict":    "max_tokens",
            "repeat_penalty": "frequency_penalty",
            "temperature":    "temperature",
            "top_p":          "top_p",
        }
        drop = {"num_ctx", "top_k", "repeat_last_n"}
        return {mapping.get(k, k): v for k, v in params.items() if k not in drop}
