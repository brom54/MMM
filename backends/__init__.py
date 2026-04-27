"""
MMM Backends
============
Each backend module handles communication with a specific inference server.
All backends inherit from BaseBackend and implement the same interface,
allowing proxy.py to work with any backend without knowing its specifics.

Adding a new backend:
1. Create backends/mybackend.py inheriting from BaseBackend
2. Implement all abstract methods
3. Register it in BACKENDS dict in this file
4. That's it — proxy.py picks it up automatically

Current backends:
    ollama    — Ollama (default, fully implemented)
    llamacpp  — llama.cpp server (stub, ready for implementation)
    lmstudio  — LM Studio (stub, ready for implementation)
    vllm      — vLLM (stub, ready for implementation)
    kobold    — Kobold.cpp (stub, ready for implementation)
"""

from .base import BaseBackend
from .ollama import OllamaBackend
from .llamacpp import LlamaCppBackend
from .lmstudio import LMStudioBackend
from .vllm import VLLMBackend
from .kobold import KoboldBackend
from .mlx import MLXBackend

# Registry — maps backend name to class
# Add new backends here
BACKENDS: dict[str, type[BaseBackend]] = {
    "ollama":   OllamaBackend,
    "llamacpp": LlamaCppBackend,
    "lmstudio": LMStudioBackend,
    "vllm":     VLLMBackend,
    "kobold":   KoboldBackend,
    "mlx":      MLXBackend,
}

def get_backend(name: str) -> type[BaseBackend]:
    """Get a backend class by name. Raises KeyError if not found."""
    if name not in BACKENDS:
        raise KeyError(f"Unknown backend: '{name}'. Available: {list(BACKENDS.keys())}")
    return BACKENDS[name]

def list_backends() -> list[str]:
    """Return list of registered backend names."""
    return list(BACKENDS.keys())
