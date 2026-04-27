"""
MMM — vLLM Backend
===================
Status: STUB — architecture in place, implementation pending.

vLLM exposes an OpenAI-compatible API and is typically used for
production/multi-user deployments rather than local single-user setups.

API docs: https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html

Key differences from Ollama:
  - OpenAI-compatible /v1/chat/completions
  - Often requires API key even for local deployments
  - Supports guided decoding (JSON schema, regex)
  - Supports LoRA adapters per-request
  - Native thinking support via reasoning_effort parameter (newer versions)
  - Much higher throughput for concurrent requests

Implementation notes for Phase 2:
  - translate_request:  Convert Ollama body to OpenAI format
  - translate_response: Convert OpenAI response to Ollama format
  - Auth handling:      vLLM often uses a bearer token even locally
  - is_available:       GET /health returns 200 if ready
  - list_models:        GET /v1/models

Parameter mapping (Ollama → vLLM):
  temperature    → temperature        (same)
  top_p          → top_p             (same)
  top_k          → top_k             (supported as extra param)
  repeat_penalty → repetition_penalty (different name)
  num_predict    → max_tokens        (different name)
  num_ctx        → (set at server startup, not per-request)
"""

import logging
from .base import BaseBackend

log = logging.getLogger("mmm.backend.vllm")

NOT_IMPLEMENTED_MSG = (
    "vLLM backend is not yet implemented. "
    "See backends/vllm.py for implementation notes. "
    "Contributions welcome: https://github.com/yourusername/MMM"
)


class VLLMBackend(BaseBackend):

    @property
    def name(self) -> str:
        return "vllm"

    @property
    def display_name(self) -> str:
        return "vLLM"

    @property
    def default_port(self) -> int:
        return 8000

    @property
    def openai_compatible(self) -> bool:
        return True

    @property
    def supports_thinking(self) -> bool:
        return True  # Via reasoning_effort in newer vLLM versions

    async def is_available(self, host: str, client) -> bool:
        try:
            resp = await client.get(f"{host}/health", timeout=3.0)
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
        raise NotImplementedError(NOT_IMPLEMENTED_MSG)

    def translate_response_chunk(self, chunk: bytes) -> bytes:
        raise NotImplementedError(NOT_IMPLEMENTED_MSG)

    def translate_response_full(self, body: bytes) -> bytes:
        raise NotImplementedError(NOT_IMPLEMENTED_MSG)

    def map_parameters(self, params: dict) -> dict:
        mapping = {
            "num_predict":    "max_tokens",
            "repeat_penalty": "repetition_penalty",
            "temperature":    "temperature",  # same
            "top_p":          "top_p",        # same
            "top_k":          "top_k",        # same (as extra param)
        }
        return {mapping.get(k, k): v for k, v in params.items()
                if k not in ("num_ctx", "repeat_last_n")}
