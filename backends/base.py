"""
MMM — BaseBackend
=================
Abstract base class all backends must implement.

A backend is responsible for three things:
1. Translating an injected MMM request body into the format the backend expects
2. Translating the backend's response back into Ollama-compatible format
   (so front-ends that expect Ollama responses keep working)
3. Reporting its capabilities so MMM knows what it can/can't do

Every method that raises NotImplementedError MUST be implemented.
Methods with default implementations MAY be overridden.
"""

from abc import ABC, abstractmethod


class BaseBackend(ABC):
    """
    Abstract base for all MMM inference backends.

    Subclasses translate between MMM's internal format (Ollama-compatible)
    and whatever format the target backend actually speaks.
    """

    # ── Identity ───────────────────────────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier, e.g. 'ollama', 'llamacpp'. Used in config and logs."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name, e.g. 'Ollama', 'llama.cpp server'."""
        ...

    @property
    def default_port(self) -> int:
        """Default port this backend listens on."""
        return 11434

    # ── Capabilities ───────────────────────────────────────────────────────

    @property
    def supports_thinking(self) -> bool:
        """Whether this backend supports the think=true/false parameter."""
        return False

    @property
    def supports_system_prompt(self) -> bool:
        """Whether this backend accepts a system role message."""
        return True

    @property
    def supports_streaming(self) -> bool:
        """Whether this backend supports streaming responses."""
        return True

    @property
    def openai_compatible(self) -> bool:
        """
        Whether this backend speaks the OpenAI chat completions API.
        If True, many translation methods can use shared OpenAI logic.
        """
        return False

    # ── Health check ───────────────────────────────────────────────────────

    @abstractmethod
    async def is_available(self, host: str, client) -> bool:
        """
        Check if this backend is running and reachable.
        Used for auto-detection.

        Args:
            host:   Base URL, e.g. 'http://localhost:11434'
            client: httpx.AsyncClient to use for the check

        Returns:
            True if the backend is reachable and responding
        """
        ...

    # ── Model listing ──────────────────────────────────────────────────────

    @abstractmethod
    async def list_models(self, host: str, client) -> list[str]:
        """
        Return a list of available model names from this backend.

        Args:
            host:   Base URL
            client: httpx.AsyncClient

        Returns:
            List of model name strings
        """
        ...

    # ── Request translation ────────────────────────────────────────────────

    @abstractmethod
    def translate_request(self, body: dict, path: str) -> tuple[dict, str]:
        """
        Translate an MMM/Ollama-format request body into this backend's format.

        Args:
            body: Request body dict (Ollama /api/chat or /api/generate format)
            path: Original request path, e.g. 'api/chat'

        Returns:
            Tuple of (translated_body, target_path)
            where target_path is the path on the backend server
        """
        ...

    # ── Response translation ───────────────────────────────────────────────

    @abstractmethod
    def translate_response_chunk(self, chunk: bytes) -> bytes:
        """
        Translate a single streaming response chunk from backend format
        to Ollama-compatible format.

        Args:
            chunk: Raw bytes from the backend

        Returns:
            Bytes in Ollama streaming response format
        """
        ...

    @abstractmethod
    def translate_response_full(self, body: bytes) -> bytes:
        """
        Translate a complete (non-streaming) response from backend format
        to Ollama-compatible format.

        Args:
            body: Complete response bytes from the backend

        Returns:
            Bytes in Ollama non-streaming response format
        """
        ...

    # ── Parameter mapping ──────────────────────────────────────────────────

    def map_parameters(self, params: dict) -> dict:
        """
        Map MMM/Ollama parameter names to this backend's parameter names.

        Default implementation returns params unchanged (suitable for
        backends that are already Ollama-compatible).

        Override this for backends with different parameter naming.

        Common Ollama params and their equivalents:
            temperature     → temperature (universal)
            top_p           → top_p (universal)
            top_k           → top_k (most backends)
            repeat_penalty  → repetition_penalty (OpenAI-style backends)
            num_ctx         → max_tokens or context_length (varies)
            num_predict     → max_new_tokens or max_tokens (varies)

        Args:
            params: Dict of Ollama-style parameter names and values

        Returns:
            Dict with parameter names translated for this backend
        """
        return params

    # ── Thinking mode ──────────────────────────────────────────────────────

    def apply_thinking(self, body: dict, think: bool) -> dict:
        """
        Apply thinking mode setting to the request body.

        Default implementation does nothing (for backends that don't
        support thinking). Override for backends that do.

        Args:
            body:  Request body dict
            think: Whether to enable thinking/reasoning

        Returns:
            Modified request body
        """
        return body

    # ── String representation ──────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name} port={self.default_port}>"
