"""
MMM — Behavior Translation Layer
==================================
Translates semantic behavior fields into provider-specific parameters.

All fields are optional. Missing fields are ignored — existing configs
and backend-specific parameter blocks are never overwritten by behavior
translation unless no backend-specific block exists.

Behavior fields:
    creativity    : very_low | low | medium | high | very_high
    response_length: brief | short | medium | long | very_long
    formality     : very_formal | formal | neutral | casual | very_casual
    reasoning     : true | false

Usage:
    from behavior import translate_behavior
    params, prompt_hint = translate_behavior(behavior_dict, backend_name)
"""

import logging

log = logging.getLogger("mmm.behavior")

# ─────────────────────────────────────────────
#  TRANSLATION TABLES
# ─────────────────────────────────────────────

# Creativity → temperature
CREATIVITY_MAP = {
    "very_low":  0.3,
    "low":       0.5,
    "medium":    0.7,
    "high":      0.85,
    "very_high": 1.0,
}

# Response length → token counts per backend family
# OpenAI-style backends use max_tokens
# Ollama uses num_predict
RESPONSE_LENGTH_MAP = {
    "brief":     256,
    "short":     512,
    "medium":    1024,
    "long":      2048,
    "very_long": 4096,
}

# Formality → system prompt hint
# neutral returns None — no hint added
FORMALITY_HINT_MAP = {
    "very_formal": "Always respond formally and professionally. Use precise language.",
    "formal":      "Maintain a professional and composed tone throughout.",
    "neutral":     None,
    "casual":      "Keep your tone conversational and relaxed.",
    "very_casual": "Be casual and informal. Never stiff or formal.",
}

# Token parameter name per backend
TOKEN_PARAM_MAP = {
    "ollama":   "num_predict",
    "llamacpp": "n_predict",
    "lmstudio": "max_tokens",
    "vllm":     "max_tokens",
    "kobold":   "max_length",
    "mlx":      "max_tokens",
    "openai":   "max_tokens",
    "anthropic":"max_tokens",
    "groq":     "max_tokens",
}

# ─────────────────────────────────────────────
#  MAIN TRANSLATION FUNCTION
# ─────────────────────────────────────────────

def translate_behavior(behavior: dict, backend_name: str) -> tuple[dict, str | None]:
    """
    Translate a behavior block into backend-specific parameters and an
    optional system prompt hint.

    Args:
        behavior:     The behavior dict from characters.json
        backend_name: The backend being targeted (e.g. 'ollama', 'openai')

    Returns:
        Tuple of:
            params       — dict of parameter key/value pairs for this backend
            prompt_hint  — string to append to system prompt, or None
    """
    if not behavior:
        return {}, None

    params = {}
    prompt_hint = None

    # ── Creativity → temperature ───────────────────────────────────────────
    creativity = behavior.get("creativity")
    if creativity is not None:
        if creativity in CREATIVITY_MAP:
            params["temperature"] = CREATIVITY_MAP[creativity]
            log.debug(f"behavior.creativity={creativity} → temperature={params['temperature']}")
        else:
            log.warning(f"Unknown creativity value '{creativity}' — ignoring. "
                        f"Valid: {list(CREATIVITY_MAP.keys())}")

    # ── Response length → token limit ──────────────────────────────────────
    response_length = behavior.get("response_length")
    if response_length is not None:
        if response_length in RESPONSE_LENGTH_MAP:
            token_count = RESPONSE_LENGTH_MAP[response_length]
            token_key   = TOKEN_PARAM_MAP.get(backend_name, "max_tokens")
            params[token_key] = token_count
            log.debug(f"behavior.response_length={response_length} → {token_key}={token_count}")
        else:
            log.warning(f"Unknown response_length value '{response_length}' — ignoring. "
                        f"Valid: {list(RESPONSE_LENGTH_MAP.keys())}")

    # ── Formality → system prompt hint ────────────────────────────────────
    formality = behavior.get("formality")
    if formality is not None:
        if formality in FORMALITY_HINT_MAP:
            prompt_hint = FORMALITY_HINT_MAP[formality]
            log.debug(f"behavior.formality={formality} → hint={'(none)' if not prompt_hint else prompt_hint[:40]}")
        else:
            log.warning(f"Unknown formality value '{formality}' — ignoring. "
                        f"Valid: {list(FORMALITY_HINT_MAP.keys())}")

    # ── Reasoning → think flag ─────────────────────────────────────────────
    # Note: reasoning is handled separately in inject_character via the
    # backend's apply_thinking() method. We don't put it in params here.
    # It's included in the behavior block for documentation purposes.

    return params, prompt_hint


def apply_behavior_to_request(body: dict, behavior: dict, backend_name: str,
                               backend_params: dict | None = None) -> dict:
    """
    Apply behavior translation to a request body.

    Priority order (highest to lowest):
        1. backend-specific parameters in characters.json  (explicit, always wins)
        2. behavior block auto-translation                  (semantic fallback)
        3. backend/Ollama defaults                         (implicit, unchanged)

    Args:
        body:          Request body dict
        behavior:      behavior block from characters.json (may be empty)
        backend_name:  Target backend name
        backend_params: Explicit backend-specific params (overrides behavior)

    Returns:
        Modified request body
    """
    # Translate behavior to params and prompt hint. Backend-specific params
    # still apply even when no behavior block exists.
    behavior_params, prompt_hint = translate_behavior(behavior or {}, backend_name)

    merged = {**behavior_params, **(backend_params or {})}
    if merged:
        # Merge: existing request/default options first, then named params.
        # The proxy may re-apply explicit request options afterward so callers
        # can still override defaults and named profiles deliberately.
        body["options"] = {**(body.get("options", {}) or {}), **merged}
        log.debug(f"Applied behavior/backend params: {merged}")

    if prompt_hint:
        # Append hint to system message if present
        messages = body.get("messages", [])
        for i, msg in enumerate(messages):
            if msg.get("role") == "system":
                body["messages"][i]["content"] = (
                    msg["content"].rstrip() + "\n\n" + prompt_hint
                )
                log.debug(f"Appended formality hint to system prompt")
                break

    return body


# ─────────────────────────────────────────────
#  VALIDATION
# ─────────────────────────────────────────────

VALID_VALUES = {
    "creativity":      list(CREATIVITY_MAP.keys()),
    "response_length": list(RESPONSE_LENGTH_MAP.keys()),
    "formality":       list(FORMALITY_HINT_MAP.keys()),
    "reasoning":       [True, False],
}

def validate_behavior(behavior: dict) -> list[str]:
    """
    Validate a behavior block and return a list of warning strings.
    Empty list means no issues.
    """
    warnings = []
    for field, value in behavior.items():
        if field not in VALID_VALUES:
            warnings.append(f"Unknown behavior field '{field}' — will be ignored")
            continue
        valid = VALID_VALUES[field]
        if value not in valid:
            warnings.append(f"Invalid value '{value}' for behavior.{field}. "
                            f"Valid: {valid}")
    return warnings
