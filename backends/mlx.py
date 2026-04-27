"""
MMM — MLX / MLX-LM Backend
============================
Status: STUB — architecture in place, implementation pending.

MLX is Apple's machine learning framework optimized for Apple Silicon
(M1/M2/M3/M4). MLX-LM provides a server mode that runs LLMs natively
on the unified memory architecture, which is significantly faster than
llama.cpp on Apple Silicon for the same model — especially at larger
sizes that spill into unified memory.

This backend is specifically for Apple Silicon Macs (M-series chips).
Intel Mac users should use the llama.cpp or LM Studio backends instead.

API docs: https://github.com/ml-explore/mlx-lm

Setup (on Apple Silicon Mac):
    pip install mlx-lm
    mlx_lm.server --model mlx-community/Qwen3-32B-4bit --port 8080

Key differences from Ollama:
  - OpenAI-compatible /v1/chat/completions endpoint
  - Model is loaded at server startup, not per-request
  - Extremely fast on Apple Silicon unified memory
  - Supports 4-bit, 8-bit quantized models from mlx-community on HuggingFace
  - No native thinking mode (thinking tokens are model-dependent)
  - Response format matches OpenAI

Recommended models (mlx-community HuggingFace):
  mlx-community/Qwen3-32B-4bit        — best quality, ~20GB unified memory
  mlx-community/Qwen3-14B-4bit        — good quality, ~10GB unified memory
  mlx-community/Meta-Llama-3.3-70B-4bit — best quality, ~40GB unified memory
  mlx-community/Mistral-7B-v0.3-4bit  — fast, low memory

Implementation notes for Phase 2:
  - translate_request:  Convert Ollama body to OpenAI /v1/chat/completions
  - translate_response: Convert OpenAI streaming/complete response to Ollama format
  - is_available:       GET /v1/models returns 200 if server is running
  - list_models:        GET /v1/models

Parameter mapping (Ollama → MLX-LM/OpenAI):
  temperature    → temperature       (same)
  top_p          → top_p            (same)
  top_k          → (not in OpenAI spec, may be ignored)
  repeat_penalty → repetition_penalty (approximate)
  num_predict    → max_tokens       (different name)
  num_ctx        → (set at server startup via --max-tokens flag)

Notes:
  - MLX-LM's server is OpenAI-compatible so the translation logic
    is nearly identical to lmstudio.py and llamacpp.py — good candidate
    for a shared OpenAI translation mixin once Phase 2 begins
  - Apple Silicon's unified memory means 32B models run well on
    64GB Mac Studios and MacBook Pros with M3/M4 Max chips
  - mlx-community on HuggingFace maintains pre-quantized versions
    of most popular models ready to run with mlx_lm.server
"""

import logging
from .base import BaseBackend

log = logging.getLogger("mmm.backend.mlx")

NOT_IMPLEMENTED_MSG = (
    "MLX backend is not yet implemented. "
    "See backends/mlx.py for implementation notes. "
    "Contributions welcome — especially from Apple Silicon users: "
    "https://github.com/yourusername/MMM"
)


class MLXBackend(BaseBackend):

    @property
    def name(self) -> str:
        return "mlx"

    @property
    def display_name(self) -> str:
        return "MLX-LM (Apple Silicon)"

    @property
    def default_port(self) -> int:
        return 8080

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
        }
        # Drop params MLX-LM doesn't support
        drop = {"num_ctx", "top_k", "repeat_last_n"}
        return {mapping.get(k, k): v for k, v in params.items() if k not in drop}
