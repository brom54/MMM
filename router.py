"""
MMM — Backend Router
=====================
Routes requests to the appropriate backend based on character config
and route table. Manages backend health state, model list caching,
multi-backend request dispatching, and token/performance statistics.

Currently wraps a single backend — architecture is in place for
multi-backend routing in Phase 2.

Route resolution order:
    1. Character config backend field (explicit per-character)
    2. Route table pattern match (top-level routes in characters.json)
    3. Default backend (BACKEND env var or 'ollama')
"""

import asyncio
import json
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

log = logging.getLogger("mmm.router")


# ─────────────────────────────────────────────
#  REQUEST STATS
#  Lightweight per-request record — collected
#  silently on every request, never shown to
#  the user unless explicitly requested via
#  /mmm/stats (Phase 4 admin UI)
# ─────────────────────────────────────────────

@dataclass
class RequestRecord:
    """Stats for a single intercepted request."""
    timestamp:              datetime
    character:              str
    model:                  str

    # Token counts from Ollama response
    prompt_tokens:          int = 0   # prompt_eval_count — total tokens model saw
    response_tokens:        int = 0   # eval_count — tokens generated
    thinking_tokens:        int = 0   # thinking tokens stripped from response

    # System prompt sizes (in characters — no tokenizer needed)
    stripped_prompt_chars:  int = 0   # front-end system prompt we removed
    injected_prompt_chars:  int = 0   # MMM system prompt we injected
    prompt_char_delta:      int = 0   # injected - stripped (negative = we saved chars)

    # Timing
    time_to_first_token_ms: float = 0.0
    total_duration_ms:      float = 0.0
    tokens_per_second:      float = 0.0

    # Flags
    was_character:          bool = True   # False = pass-through
    had_thinking:           bool = False


@dataclass
class CharacterStats:
    """Aggregate stats for a character, computed on demand."""
    character:                      str
    total_requests:                 int = 0

    # Token totals
    total_prompt_tokens:            int = 0
    total_response_tokens:          int = 0
    total_thinking_tokens_stripped: int = 0

    # System prompt delta totals
    total_stripped_chars:           int = 0
    total_injected_chars:           int = 0
    total_char_delta:               int = 0

    # Averages
    avg_prompt_tokens:              float = 0.0
    avg_response_tokens:            float = 0.0
    avg_thinking_tokens_stripped:   float = 0.0
    avg_tokens_per_second:          float = 0.0
    avg_time_to_first_token_ms:     float = 0.0
    avg_stripped_chars:             float = 0.0
    avg_injected_chars:             float = 0.0
    avg_char_delta:                 float = 0.0


class StatsCollector:
    """
    Silent token and performance stats collector.

    Collects data on every request. Aggregates on demand.
    No user-facing output until explicitly requested.

    Phase 4: surfaces via /mmm/stats endpoint and admin UI.
    """

    def __init__(self, max_records: int = 1000):
        # Rolling window of recent records per character
        # Capped at max_records to avoid unbounded memory growth
        self._records: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=max_records)
        )
        self._lock = asyncio.Lock()

    async def record(self, record: RequestRecord):
        """Add a request record. Called after every completed request."""
        async with self._lock:
            self._records[record.character].append(record)

    def get_character_stats(self, character: str) -> Optional[CharacterStats]:
        """Compute aggregate stats for a character from recorded data."""
        records = list(self._records.get(character, []))
        if not records:
            return None

        stats = CharacterStats(character=character)
        stats.total_requests = len(records)

        timing_records = [r for r in records if r.tokens_per_second > 0]

        stats.total_prompt_tokens            = sum(r.prompt_tokens for r in records)
        stats.total_response_tokens          = sum(r.response_tokens for r in records)
        stats.total_thinking_tokens_stripped = sum(r.thinking_tokens for r in records)
        stats.total_stripped_chars           = sum(r.stripped_prompt_chars for r in records)
        stats.total_injected_chars           = sum(r.injected_prompt_chars for r in records)
        stats.total_char_delta               = sum(r.prompt_char_delta for r in records)

        n = stats.total_requests
        stats.avg_prompt_tokens            = stats.total_prompt_tokens / n
        stats.avg_response_tokens          = stats.total_response_tokens / n
        stats.avg_thinking_tokens_stripped = stats.total_thinking_tokens_stripped / n
        stats.avg_stripped_chars           = stats.total_stripped_chars / n
        stats.avg_injected_chars           = stats.total_injected_chars / n
        stats.avg_char_delta               = stats.total_char_delta / n

        if timing_records:
            t = len(timing_records)
            stats.avg_tokens_per_second       = sum(r.tokens_per_second for r in timing_records) / t
            stats.avg_time_to_first_token_ms  = sum(r.time_to_first_token_ms for r in timing_records) / t

        return stats

    def get_all_stats(self) -> dict[str, CharacterStats]:
        """Get aggregate stats for all characters."""
        return {
            char: self.get_character_stats(char)
            for char in self._records
            if self._records[char]
        }

    def get_raw_records(self, character: str, limit: int = 50) -> list[RequestRecord]:
        """Get recent raw records for a character. For dev/debug use."""
        records = list(self._records.get(character, []))
        return records[-limit:]

    def total_requests(self) -> int:
        return sum(len(v) for v in self._records.values())

    def total_thinking_tokens_stripped(self) -> int:
        return sum(
            r.thinking_tokens
            for records in self._records.values()
            for r in records
        )

    def total_char_delta(self) -> int:
        """Total characters saved across all requests (negative = saved)."""
        return sum(
            r.prompt_char_delta
            for records in self._records.values()
            for r in records
        )


# ─────────────────────────────────────────────
#  BACKEND ROUTER
# ─────────────────────────────────────────────

class BackendRouter:
    """
    Routes requests to backends, manages health state, model cache,
    and collects token/performance statistics.

    Phase 1: Single backend, full health check and model cache support.
    Phase 2: Multi-backend routing, failover chains, route table.
    """

    def __init__(self, default_backend, default_host: str,
                 refresh_hours: float = 6.0):
        self.default_backend  = default_backend
        self.default_host     = default_host
        self.refresh_hours    = refresh_hours

        # ── Stats collector ────────────────────────────────────────────
        self.stats = StatsCollector()

        # ── Model cache ────────────────────────────────────────────────
        self._model_cache: list[str] = []
        self._cache_updated: Optional[datetime] = None
        self._cache_lock = asyncio.Lock()

        # ── Health state ───────────────────────────────────────────────
        self._healthy: bool = False
        self._health_checked: Optional[datetime] = None

        # ── Future: registered backends ───────────────────────────────
        # Phase 2: self._backends: dict[str, tuple[BaseBackend, str]] = {}
        # Phase 2: self._routes: list[dict] = []
        # Phase 2: self._failover_chains: dict[str, list[str]] = {}

    # ── Health ─────────────────────────────────────────────────────────

    async def check_health(self, client) -> bool:
        try:
            self._healthy = await self.default_backend.is_available(
                self.default_host, client
            )
            self._health_checked = datetime.now(timezone.utc)
            status = "healthy" if self._healthy else "unreachable"
            log.info(f"Health check: {self.default_backend.display_name} is {status}")
            return self._healthy
        except Exception as e:
            self._healthy = False
            log.warning(f"Health check failed: {e}")
            return False

    @property
    def is_healthy(self) -> bool:
        return self._healthy

    # ── Model cache ────────────────────────────────────────────────────

    async def refresh_models(self, client) -> list[str]:
        async with self._cache_lock:
            try:
                models = await self.default_backend.list_models(
                    self.default_host, client
                )
                self._model_cache = models
                self._cache_updated = datetime.now(timezone.utc)
                log.info(f"Model cache updated: {len(models)} model(s)")
                return models
            except Exception as e:
                log.warning(f"Could not refresh model list: {e}")
                return self._model_cache

    def has_model(self, model_name: str) -> bool:
        if not self._model_cache:
            return True
        return any(
            m == model_name or m.startswith(model_name)
            for m in self._model_cache
        )

    def needs_refresh(self) -> bool:
        if self.refresh_hours <= 0:
            return False
        if self._cache_updated is None:
            return True
        age = datetime.now(timezone.utc) - self._cache_updated
        return age > timedelta(hours=self.refresh_hours)

    @property
    def cached_models(self) -> list[str]:
        return list(self._model_cache)

    @property
    def cache_age_minutes(self) -> Optional[float]:
        if self._cache_updated is None:
            return None
        age = datetime.now(timezone.utc) - self._cache_updated
        return round(age.total_seconds() / 60, 1)

    # ── Route resolution ───────────────────────────────────────────────

    def resolve(self, model_name: str, character: Optional[dict] = None) -> tuple:
        # Phase 2 will add per-character and route table resolution
        return self.default_backend, self.default_host

    # ── Validation ─────────────────────────────────────────────────────

    def validate_request(self, model_name: str,
                         character: Optional[dict] = None) -> Optional[str]:
        if not self._healthy and self._health_checked is not None:
            return (f"Backend '{self.default_backend.display_name}' is not available. "
                    f"Last checked: {self._health_checked.strftime('%H:%M:%S')}")

        check_model = model_name
        if character and character.get("base_model"):
            check_model = character["base_model"]

        if self._model_cache and not self.has_model(check_model):
            return (f"Model '{check_model}' not found in "
                    f"{self.default_backend.display_name}. "
                    f"Available: {', '.join(self._model_cache[:5])}"
                    f"{'...' if len(self._model_cache) > 5 else ''}")

        return None

    def make_error_response(self, model_name: str, error_msg: str) -> bytes:
        payload = {
            "model":       model_name,
            "created_at":  datetime.now(timezone.utc).isoformat(),
            "message":     {"role": "assistant", "content": ""},
            "done":        True,
            "done_reason": "error",
            "error":       error_msg
        }
        return json.dumps(payload).encode() + b"\n"

    # ── Stats helpers ──────────────────────────────────────────────────

    def build_record(self, character: str, model: str,
                     stripped_prompt: str, injected_prompt: str) -> RequestRecord:
        """
        Create a RequestRecord at request time with prompt size data.
        Timing and token counts are filled in after the response completes.
        """
        stripped_chars  = len(stripped_prompt)
        injected_chars  = len(injected_prompt)
        return RequestRecord(
            timestamp             = datetime.now(timezone.utc),
            character             = character,
            model                 = model,
            stripped_prompt_chars = stripped_chars,
            injected_prompt_chars = injected_chars,
            prompt_char_delta     = injected_chars - stripped_chars,
        )

    def update_record_from_response(self, record: RequestRecord,
                                     response_body: dict):
        """
        Fill in token counts and timing from Ollama's response body.
        Called after a complete (non-streaming) response is received.
        """
        record.prompt_tokens   = response_body.get("prompt_eval_count", 0)
        record.response_tokens = response_body.get("eval_count", 0)

        # Total duration from Ollama is in nanoseconds
        total_ns = response_body.get("total_duration", 0)
        if total_ns:
            record.total_duration_ms = total_ns / 1_000_000

        # Tokens per second
        eval_ns = response_body.get("eval_duration", 0)
        if eval_ns and record.response_tokens:
            record.tokens_per_second = record.response_tokens / (eval_ns / 1_000_000_000)

    # ── Status ─────────────────────────────────────────────────────────

    def status(self) -> dict:
        all_stats = self.stats.get_all_stats()
        return {
            "healthy":                     self._healthy,
            "backend":                     self.default_backend.display_name,
            "host":                        self.default_host,
            "models_cached":               len(self._model_cache),
            "cache_age_mins":              self.cache_age_minutes,
            "health_checked":              self._health_checked.isoformat() if self._health_checked else None,
            "total_requests":              self.stats.total_requests(),
            "total_thinking_stripped":     self.stats.total_thinking_tokens_stripped(),
            "total_prompt_char_delta":     self.stats.total_char_delta(),
            "characters": {
                char: {
                    "requests":              s.total_requests,
                    "avg_response_tokens":   round(s.avg_response_tokens, 1),
                    "avg_tok_per_sec":       round(s.avg_tokens_per_second, 2),
                    "avg_thinking_stripped": round(s.avg_thinking_tokens_stripped, 1),
                    "avg_prompt_char_delta": round(s.avg_char_delta, 0),
                }
                for char, s in all_stats.items()
            }
        }
