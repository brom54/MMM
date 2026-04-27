"""
MMM — Kobold.cpp Backend
=========================
Status: STUB — architecture in place, implementation pending.

Kobold.cpp has its own native API that is NOT OpenAI-compatible.
It also has a lite API mode. This makes it the most different from
the other backends and the most work to implement.

API docs: https://lite.koboldai.net/koboldcpp_api

Key differences from Ollama:
  - Native Kobold API at /api/v1/generate (NOT OpenAI-compatible)
  - Also has KoboldAI Lite API
  - Single /api/v1/generate endpoint (no chat vs completion split)
  - Manages conversation history differently — no messages array
  - Rich sampler controls (mirostat, tfs_z, typical_p, etc.)
  - Memory, world info, author's note fields
  - No native thinking mode

Implementation notes for Phase 2:
  - translate_request:  Convert Ollama messages array to Kobold prompt string
                        (requires assembling the conversation into a single prompt)
  - translate_response: Convert Kobold response to Ollama streaming/complete format
  - is_available:       GET /api/v1/info/version
  - list_models:        GET /api/v1/model

Parameter mapping (Ollama → Kobold):
  temperature    → temperature        (same)
  top_p          → top_p             (same)
  top_k          → top_k             (same)
  repeat_penalty → rep_pen           (different name)
  num_predict    → max_length        (different name)
  num_ctx        → max_context_length (different name)

Extra Kobold params worth exposing:
  rep_pen_range  → repeat penalty range
  rep_pen_slope  → repeat penalty slope
  tfs            → tail-free sampling
  typical        → typical sampling
  mirostat       → mirostat sampling mode (0/1/2)
  mirostat_tau   → mirostat target entropy
  mirostat_eta   → mirostat learning rate
"""

import logging
from .base import BaseBackend

log = logging.getLogger("mmm.backend.kobold")

NOT_IMPLEMENTED_MSG = (
    "Kobold.cpp backend is not yet implemented. "
    "See backends/kobold.py for implementation notes. "
    "Contributions welcome: https://github.com/yourusername/MMM"
)


class KoboldBackend(BaseBackend):

    @property
    def name(self) -> str:
        return "kobold"

    @property
    def display_name(self) -> str:
        return "Kobold.cpp"

    @property
    def default_port(self) -> int:
        return 5001

    @property
    def openai_compatible(self) -> bool:
        return False  # Kobold has its own API

    async def is_available(self, host: str, client) -> bool:
        try:
            resp = await client.get(f"{host}/api/v1/info/version", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self, host: str, client) -> list[str]:
        try:
            resp = await client.get(f"{host}/api/v1/model")
            data = resp.json()
            return [data.get("result", "(loaded model)")]
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
            "num_predict":    "max_length",
            "num_ctx":        "max_context_length",
            "repeat_penalty": "rep_pen",
            "temperature":    "temperature",  # same
            "top_p":          "top_p",        # same
            "top_k":          "top_k",        # same
        }
        return {mapping.get(k, k): v for k, v in params.items()}
