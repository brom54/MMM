"""
MMM — llama.cpp Server Backend
================================
Status: STUB — architecture in place, implementation pending.

llama.cpp server exposes an OpenAI-compatible API at /v1/chat/completions
as well as its own native endpoints at /completion and /tokenize.

API docs: https://github.com/ggerganov/llama.cpp/blob/master/examples/server/README.md

Key differences from Ollama:
  - OpenAI-compatible /v1/chat/completions endpoint
  - No model switching — model is loaded at server startup
  - Parameter names differ (n_predict vs num_predict, etc.)
  - No native thinking/reasoning mode
  - Response format matches OpenAI, not Ollama

Implementation notes for Phase 2:
  - translate_request:  Convert Ollama /api/chat body to OpenAI /v1/chat/completions
  - translate_response: Convert OpenAI streaming chunks to Ollama streaming format
  - map_parameters:     Map Ollama param names to llama.cpp param names
  - is_available:       GET /health returns {"status": "ok"}
  - list_models:        GET /v1/models or return the single loaded model

Parameter mapping (Ollama → llama.cpp):
  temperature    → temperature       (same)
  top_p          → top_p             (same)
  top_k          → top_k             (same)
  repeat_penalty → repeat_penalty    (same)
  num_ctx        → n_ctx             (different)
  num_predict    → n_predict         (different)
"""

import logging
from .base import BaseBackend

log = logging.getLogger("mmm.backend.llamacpp")

NOT_IMPLEMENTED_MSG = (
    "llama.cpp backend is not yet implemented. "
    "See backends/llamacpp.py for implementation notes. "
    "Contributions welcome: https://github.com/yourusername/MMM"
)


class LlamaCppBackend(BaseBackend):

    @property
    def name(self) -> str:
        return "llamacpp"

    @property
    def display_name(self) -> str:
        return "llama.cpp server"

    @property
    def default_port(self) -> int:
        return 8080

    @property
    def openai_compatible(self) -> bool:
        return True

    async def is_available(self, host: str, client) -> bool:
        try:
            resp = await client.get(f"{host}/health", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self, host: str, client) -> list[str]:
        # llama.cpp serves one model — try to get its name
        try:
            resp = await client.get(f"{host}/v1/models")
            data = resp.json()
            return [m["id"] for m in data.get("data", [])]
        except Exception:
            return ["(loaded model)"]

    def translate_request(self, body: dict, path: str) -> tuple[dict, str]:
        raise NotImplementedError(NOT_IMPLEMENTED_MSG)

    def translate_response_chunk(self, chunk: bytes) -> bytes:
        raise NotImplementedError(NOT_IMPLEMENTED_MSG)

    def translate_response_full(self, body: bytes) -> bytes:
        raise NotImplementedError(NOT_IMPLEMENTED_MSG)

    def map_parameters(self, params: dict) -> dict:
        # Parameter name mapping — ready for implementation
        mapping = {
            "num_ctx":        "n_ctx",
            "num_predict":    "n_predict",
            "repeat_penalty": "repeat_penalty",  # same
            "temperature":    "temperature",      # same
            "top_p":          "top_p",            # same
            "top_k":          "top_k",            # same
        }
        return {mapping.get(k, k): v for k, v in params.items()}
