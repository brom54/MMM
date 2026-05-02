#!/usr/bin/env python3
"""
MMM — Make Modelfiles Matter
=============================
A universal AI consistency proxy. Define your agent once — personality,
parameters, response style, behavior — and MMM enforces that definition
across every model, every provider, and every front-end.

Usage:
    python3 proxy.py

Environment variables:
    OLLAMA_HOST           Backend URL              (default: http://localhost:11434)
    PROXY_PORT            Port to listen on        (default: 11435)
    BACKEND               Backend name             (default: ollama)
    CONFIG_FILE           Path to characters.json  (default: ./characters.json)
    HEARTBEAT_INTERVAL    Seconds between keepalive pings (default: 3)
    MODEL_REFRESH_HOURS   Hours between model cache refresh (default: 6, 0=never)

https://github.com/yourusername/MMM
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv optional — env vars can be set directly
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from backends import get_backend, list_backends
from behavior import apply_behavior_to_request, validate_behavior
from router import BackendRouter
from auth import create_auth_middleware, RequestContext
from watcher import ModelfileWatcher
from secrets_provider import secrets
from database import (
    init_db, bootstrap_from_env,
    create_identity, list_identities, revoke_identity, rotate_key,
    log_request, query_request_log
)

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
OLLAMA_HOST        = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_API_KEY     = os.getenv("OLLAMA_API_KEY", "")         # Bearer token for OLLAMA_HOST
PROXY_PORT         = int(os.getenv("PROXY_PORT", "11435"))
BACKEND_NAME       = os.getenv("BACKEND", "ollama")
CONFIG_FILE        = Path(os.getenv("CONFIG_FILE", Path(__file__).parent / "characters.json"))
HEARTBEAT_INTERVAL = float(os.getenv("HEARTBEAT_INTERVAL", "3"))
MODEL_REFRESH_HOURS= float(os.getenv("MODEL_REFRESH_HOURS", "6"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("mmm")

# ─────────────────────────────────────────────
#  BACKEND + ROUTER
# ─────────────────────────────────────────────
try:
    backend = get_backend(BACKEND_NAME)()
    log.info(f"Backend: {backend.display_name}")
except KeyError:
    log.error(f"Unknown backend '{BACKEND_NAME}'. Available: {list_backends()}")
    raise SystemExit(1)

router = BackendRouter(
    default_backend=backend,
    default_host=OLLAMA_HOST,
    refresh_hours=MODEL_REFRESH_HOURS
)

# ─────────────────────────────────────────────
#  CHARACTER CONFIG
# ─────────────────────────────────────────────
def load_config() -> tuple[dict, dict]:
    if not CONFIG_FILE.exists():
        log.warning(f"Config file not found: {CONFIG_FILE}")
        return {}, {}
    with open(CONFIG_FILE) as f:
        data = json.load(f)

    defaults = data.get("defaults", {}) or {}
    characters = data.get("characters", {}) or {}

    # Validate behavior blocks on load
    for name, char in characters.items():
        behavior = char.get("behavior", {})
        if behavior:
            warnings = validate_behavior(behavior)
            for w in warnings:
                log.warning(f"Character '{name}': {w}")

    default_params = defaults.get("parameters", {}) or {}
    log.info(
        f"Loaded defaults: {len(default_params)} parameter(s); "
        f"{len(characters)} character(s): {', '.join(characters.keys())}"
    )
    return defaults, characters

DEFAULTS, CHARACTERS = load_config()

# ─────────────────────────────────────────────
#  BYPASS MODE
#  When True, MMM passes all requests through
#  untouched — no injection, no stripping, no
#  character matching. Pure transparent proxy.
#  Toggle via /mmm/bypass endpoints.
# ─────────────────────────────────────────────
BYPASS_MODE: bool = False
watcher = ModelfileWatcher(CHARACTERS)

# ─────────────────────────────────────────────
#  HTTP CLIENT
# ─────────────────────────────────────────────
http_client: httpx.AsyncClient = None

async def startup_refresh():
    """Run health check and model cache refresh on startup."""
    await router.check_health(http_client)
    if router.is_healthy:
        await router.refresh_models(http_client)
    else:
        log.warning("Backend unavailable at startup — model validation disabled until backend comes online")

async def auto_refresh_loop():
    """Background task: periodically refresh model cache."""
    if MODEL_REFRESH_HOURS <= 0:
        return
    while True:
        await asyncio.sleep(MODEL_REFRESH_HOURS * 3600)
        if await router.check_health(http_client):
            await router.refresh_models(http_client)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    # Initialize database
    init_db()
    bootstrap_from_env()

    http_client = httpx.AsyncClient(timeout=300.0)
    log.info("HTTP client ready")

    await startup_refresh()
    refresh_task = asyncio.create_task(auto_refresh_loop())
    watcher.start()

    yield

    watcher.stop()
    refresh_task.cancel()
    await http_client.aclose()
    log.info("HTTP client closed")

app = FastAPI(title="MMM — Make Modelfiles Matter", lifespan=lifespan)
create_auth_middleware(app)

# ─────────────────────────────────────────────
#  HEARTBEAT
# ─────────────────────────────────────────────
def make_heartbeat(model: str) -> bytes:
    payload = {
        "model":      model,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "message":    {"role": "assistant", "content": ""},
        "done":       False
    }
    return json.dumps(payload).encode() + b"\n"

async def stream_with_heartbeat(request_method, url, params, headers,
                                 body_bytes, model, stat_record=None):
    first_token_received = False

    async def heartbeat_generator(queue: asyncio.Queue):
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                queue.put_nowait(("heartbeat", make_heartbeat(model)))
            except asyncio.QueueFull:
                pass

    async def backend_generator(queue: asyncio.Queue):
        try:
            async with http_client.stream(
                method=request_method,
                url=url,
                params=params,
                headers=headers,
                content=body_bytes,
            ) as resp:
                async for chunk in resp.aiter_bytes():
                    if chunk.strip():
                        queue.put_nowait(("chunk", chunk))
        finally:
            queue.put_nowait(("done", None))

    queue = asyncio.Queue(maxsize=100)
    heartbeat_task = asyncio.create_task(heartbeat_generator(queue))
    backend_task   = asyncio.create_task(backend_generator(queue))

    try:
        while True:
            kind, data = await queue.get()
            if kind == "done":
                break
            if kind == "chunk":
                if not first_token_received:
                    first_token_received = True
                    heartbeat_task.cancel()
                    log.info("First token received — heartbeat stopped")
                translated = backend.translate_response_chunk(data)
                # Capture stats from final done chunk
                if stat_record is not None:
                    try:
                        chunk_data = json.loads(data)
                        if chunk_data.get("done") is True:
                            router.update_record_from_response(stat_record, chunk_data)
                            asyncio.create_task(router.stats.record(stat_record))
                            mmm_ctx = getattr(request.state, "mmm_ctx", None) if hasattr(request, "state") else None
                    except Exception:
                        pass
                yield translated
            elif kind == "heartbeat" and not first_token_received:
                yield data
    finally:
        heartbeat_task.cancel()
        backend_task.cancel()
        for task in [heartbeat_task, backend_task]:
            try:
                await task
            except asyncio.CancelledError:
                pass

# ─────────────────────────────────────────────
#  CHARACTER INJECTION
# ─────────────────────────────────────────────
def apply_defaults_to_request(body: dict, defaults: dict,
                              backend_name: str,
                              request_options: dict | None = None) -> dict:
    """
    Apply global defaults to every generation request.

    Merge order is intentional:
        1. defaults.parameters
        2. explicit request options

    Character/backend overrides are applied later by inject_character(), with
    explicit request options still winning last.
    """
    params = (defaults or {}).get("parameters", {}) or {}
    if params:
        mapped = backend.map_parameters(params) if hasattr(backend, "map_parameters") else params
        body["options"] = {**mapped, **(body.get("options", {}) or {})}

    keep_alive = (defaults or {}).get("keep_alive")
    if keep_alive is not None and "keep_alive" not in body:
        body["keep_alive"] = keep_alive

    # Thinking is an Ollama request-level field, not an options parameter.
    # Default it here so pass-through models can still suppress thinking output
    # unless the caller explicitly asks otherwise.
    if "think" in (defaults or {}) and "think" not in body:
        body["think"] = defaults["think"]

    return body


def inject_character(body: dict, character: dict, resolved_backend,
                     backend_name: str,
                     request_options: dict | None = None) -> dict:
    system_prompt   = character.get("system_prompt", "")
    behavior        = character.get("behavior", {})
    think           = character.get("think", False)
    model_name      = character.get("base_model")

    # Per-backend parameter override (optional)
    backend_block   = character.get("backends", {}).get(backend_name, {})
    backend_params  = backend_block.get("parameters", {})
    if backend_block.get("base_model"):
        model_name = backend_block["base_model"]

    # Remap to base model
    if model_name:
        body["model"] = model_name

    # Strip front-end system prompt, inject ours
    if "messages" in body:
        body["messages"] = [m for m in body["messages"] if m.get("role") != "system"]
        if system_prompt:
            body["messages"].insert(0, {"role": "system", "content": system_prompt})

    if "system" in body or "prompt" in body:
        if system_prompt:
            body["system"] = system_prompt

    # Apply behavior translation (with backend-specific override)
    if behavior or backend_params:
        body = apply_behavior_to_request(body, behavior, backend_name, backend_params)

        # Preserve intended precedence:
        # defaults < named character/model params < explicit request options.
        if request_options:
            body["options"] = {**(body.get("options", {}) or {}), **request_options}
    elif character.get("parameters"):
        # Legacy: top-level parameters block (backwards compatible).
        # Preserve precedence: defaults < legacy params < explicit request options.
        mapped = resolved_backend.map_parameters(character["parameters"])
        body["options"] = {
            **(body.get("options", {}) or {}),
            **mapped,
            **(request_options or {}),
        }

    # Apply thinking mode
    if resolved_backend.supports_thinking:
        body = resolved_backend.apply_thinking(body, think)
        log.info(f"  think={think}")

    return body

# ─────────────────────────────────────────────
#  MMM ADMIN ENDPOINTS
# ─────────────────────────────────────────────
@app.get("/mmm/status")
async def mmm_status():
    """Current MMM status — backend health, model cache, config."""
    return JSONResponse({
        "mmm":        "Make Modelfiles Matter",
        "bypass":     BYPASS_MODE,
        "router":     router.status(),
        "defaults":   DEFAULTS,
        "characters": list(CHARACTERS.keys()),
        "config":     str(CONFIG_FILE),
    })

@app.post("/mmm/refresh")
async def mmm_refresh():
    """Refresh model cache and rescan modelfiles directory."""
    log.info("Manual refresh requested")

    # Rescan modelfiles directory and reload characters/defaults
    watcher.trigger()
    global DEFAULTS, CHARACTERS
    DEFAULTS, CHARACTERS = load_config()

    # Refresh model cache from backend
    await router.check_health(http_client)
    if router.is_healthy:
        models = await router.refresh_models(http_client)
        return JSONResponse({
            "status":     "refreshed",
            "models":     models,
            "count":      len(models),
            "characters": list(CHARACTERS.keys())
        })
    else:
        return JSONResponse({
            "status":     "error",
            "error":      f"Backend '{backend.display_name}' is not available",
            "characters": list(CHARACTERS.keys())
        }, status_code=503)

@app.get("/mmm/models")
async def mmm_models():
    """List cached models."""
    return JSONResponse({
        "models":    router.cached_models,
        "count":     len(router.cached_models),
        "cache_age_mins": router.cache_age_minutes
    })


# ─────────────────────────────────────────────
#  BYPASS MODE ENDPOINTS
# ─────────────────────────────────────────────
@app.post("/mmm/bypass/on")
async def mmm_bypass_on():
    """Enable bypass mode — MMM becomes a transparent proxy, no injection."""
    global BYPASS_MODE
    BYPASS_MODE = True
    log.info("BYPASS MODE ENABLED — all requests pass through untouched")
    return JSONResponse({"bypass": True, "message": "MMM is now in bypass mode. All requests pass through without injection."})

@app.post("/mmm/bypass/off")
async def mmm_bypass_off():
    """Disable bypass mode — MMM resumes character injection."""
    global BYPASS_MODE
    BYPASS_MODE = False
    log.info("BYPASS MODE DISABLED — character injection resumed")
    return JSONResponse({"bypass": False, "message": "MMM is active. Character injection resumed."})

@app.get("/mmm/bypass")
async def mmm_bypass_status():
    """Check current bypass mode status."""
    return JSONResponse({"bypass": BYPASS_MODE})

# ─────────────────────────────────────────────
#  KEY MANAGEMENT ENDPOINTS
# ─────────────────────────────────────────────
@app.post("/mmm/keys/generate")
async def mmm_keys_generate(request: Request):
    """
    Generate a new API key.
    The plain key is returned ONCE — store it securely.
    If lost, rotate the key to generate a new one.

    Body: {"label": "name-for-this-key", "type": "service"|"user", "role": "user"|"admin"}
    """
    ctx = getattr(request.state, "mmm_ctx", None)
    if ctx and not ctx.is_admin:
        return JSONResponse({"error": "Admin access required"}, status_code=403)

    try:
        data  = await request.json()
        label = data.get("label", "").strip()
        ktype = data.get("type", "service")
        role  = data.get("role", "user")
    except Exception:
        return JSONResponse({"error": "Invalid request body"}, status_code=400)

    if not label:
        return JSONResponse({"error": "label is required"}, status_code=400)

    identity, plain_key = create_identity(label=label, type=ktype, role=role)

    return JSONResponse({
        "id":         identity.id,
        "label":      identity.label,
        "type":       identity.type,
        "role":       identity.role,
        "created_at": identity.created_at,
        "key":        plain_key,
        "warning":    "Store this key securely. It will not be shown again."
    })


@app.get("/mmm/keys")
async def mmm_keys_list(request: Request):
    """List all identities. Never returns key values."""
    ctx = getattr(request.state, "mmm_ctx", None)
    if ctx and not ctx.is_admin:
        return JSONResponse({"error": "Admin access required"}, status_code=403)

    identities = list_identities()
    return JSONResponse({
        "identities": [
            {
                "id":         i.id,
                "label":      i.label,
                "type":       i.type,
                "role":       i.role,
                "active":     i.active,
                "created_at": i.created_at,
                "last_used":  i.last_used,
            }
            for i in identities
        ],
        "count": len(identities)
    })


@app.post("/mmm/keys/{identity_id}/revoke")
async def mmm_keys_revoke(identity_id: str, request: Request):
    """Revoke an API key. Requests using it will be rejected immediately."""
    ctx = getattr(request.state, "mmm_ctx", None)
    if ctx and not ctx.is_admin:
        return JSONResponse({"error": "Admin access required"}, status_code=403)

    if revoke_identity(identity_id):
        return JSONResponse({"status": "revoked", "id": identity_id})
    return JSONResponse({"error": "Identity not found"}, status_code=404)


@app.post("/mmm/keys/{identity_id}/rotate")
async def mmm_keys_rotate(identity_id: str, request: Request):
    """
    Rotate an API key — generate a new key for an existing identity.
    Old key is immediately invalidated.
    New key is returned ONCE.
    """
    ctx = getattr(request.state, "mmm_ctx", None)
    if ctx and not ctx.is_admin:
        return JSONResponse({"error": "Admin access required"}, status_code=403)

    plain_key = rotate_key(identity_id)
    if plain_key:
        return JSONResponse({
            "id":      identity_id,
            "key":     plain_key,
            "warning": "Store this key securely. It will not be shown again."
        })
    return JSONResponse({"error": "Identity not found or inactive"}, status_code=404)


@app.get("/mmm/audit")
async def mmm_audit(request: Request, limit: int = 100,
                    identity_id: str = None, character: str = None):
    """Query the persistent request audit log."""
    ctx = getattr(request.state, "mmm_ctx", None)
    if ctx and not ctx.is_admin:
        return JSONResponse({"error": "Admin access required"}, status_code=403)

    records = query_request_log(
        identity_id = identity_id,
        character   = character,
        limit       = limit
    )
    return JSONResponse({"records": records, "count": len(records)})

# ─────────────────────────────────────────────
#  PROXY
# ─────────────────────────────────────────────
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy(request: Request, path: str):
    body_bytes      = await request.body()
    headers         = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "authorization")}
    if OLLAMA_API_KEY:
        headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"
    is_character    = False
    model_name      = "unknown"
    character       = None
    stat_record     = None
    original_system = ""   # front-end system prompt before MMM strips it

    if path in ("api/chat", "api/generate") and body_bytes:
        try:
            body = json.loads(body_bytes)
            requested_model = body.get("model", "")
            model_name = requested_model
            request_options = dict(body.get("options", {}) or {})

            # Global defaults apply to every generation request, including
            # pass-through model requests. Named character/model settings may
            # override these later; explicit request options win last.
            body = apply_defaults_to_request(body, DEFAULTS, BACKEND_NAME, request_options)
            body_bytes = json.dumps(body).encode()
            headers["content-length"] = str(len(body_bytes))
            headers["content-type"] = "application/json"

            # Capture front-end system prompt BEFORE injection
            # This is what MMM strips — used for stats delta
            original_system = next(
                (m.get("content", "") for m in body.get("messages", [])
                 if m.get("role") == "system"),
                ""
            )

            # Skip character matching in bypass mode
            if BYPASS_MODE:
                matched_key = None
            else:
                matched_key = next(
                    (k for k in CHARACTERS if requested_model == k or requested_model.startswith(k)),
                    None
                )

            character = CHARACTERS.get(matched_key) if matched_key else None

            # ── Validate request before proceeding ────────────────────
            error_msg = router.validate_request(requested_model, character)
            if error_msg:
                log.warning(f"Request rejected: {error_msg}")
                error_chunk = router.make_error_response(requested_model, error_msg)
                return StreamingResponse(
                    iter([error_chunk]),
                    media_type="application/x-ndjson"
                )

            if matched_key:
                log.info(f"Intercepting '{requested_model}' → injecting '{matched_key}'")
                resolved_backend, resolved_host = router.resolve(requested_model, character)
                body = inject_character(
                    body, character, resolved_backend, BACKEND_NAME, request_options
                )
                body, path = resolved_backend.translate_request(body, path)
                body_bytes = json.dumps(body).encode()
                headers["content-length"] = str(len(body_bytes))
                headers["content-type"]   = "application/json"
                model_name   = body.get("model", requested_model)
                is_character = True

                # Build stats record — prompt sizes captured at request time
                stat_record = router.build_record(
                    character       = matched_key,
                    model           = model_name,
                    stripped_prompt = original_system,
                    injected_prompt = character.get("system_prompt", ""),
                )
                # Attach identity for audit attribution
                mmm_ctx = getattr(request.state, "mmm_ctx", None)
                stat_identity = mmm_ctx.identity if mmm_ctx else None
            else:
                log.info(f"Pass-through: '{requested_model}'")
                resolved_backend, resolved_host = router.resolve(requested_model)

        except json.JSONDecodeError:
            log.warning("Non-JSON body — passing through raw")
            resolved_host = OLLAMA_HOST
    else:
        resolved_host = OLLAMA_HOST

    target_url = f"{resolved_host}/{path}"
    params     = dict(request.query_params)

    wants_stream = True
    try:
        if json.loads(body_bytes).get("stream") is False:
            wants_stream = False
    except Exception:
        pass

    if wants_stream:
        return StreamingResponse(
            stream_with_heartbeat(
                request.method, target_url, params, headers, body_bytes, model_name
            ),
            media_type="application/x-ndjson" if path in ("api/chat", "api/generate") else "application/json"
        )
    else:
        resp = await http_client.request(
            method  = request.method,
            url     = target_url,
            params  = params,
            headers = headers,
            content = body_bytes,
        )
        clean = backend.translate_response_full(resp.content)

        # Update stats record with token counts from response
        if stat_record is not None:
            try:
                resp_data = json.loads(clean)
                router.update_record_from_response(stat_record, resp_data)
                await router.stats.record(stat_record)
                log_request(stat_record, stat_identity)
            except Exception:
                pass

        return Response(
            content     = clean,
            status_code = resp.status_code,
            headers     = {k: v for k, v in resp.headers.items() if k.lower() != "content-length"},
            media_type  = resp.headers.get("content-type")
        )

# ─────────────────────────────────────────────
#  ENTRYPOINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    log.info(f"MMM — Make Modelfiles Matter")
    log.info(f"Backend:        {backend.display_name}")
    log.info(f"Proxy port:     {PROXY_PORT}")
    log.info(f"Target:         {OLLAMA_HOST}")
    log.info(f"Heartbeat:      every {HEARTBEAT_INTERVAL}s")
    log.info(f"Model refresh:  every {MODEL_REFRESH_HOURS}h")
    log.info(f"Characters:     {list(CHARACTERS.keys())}")
    uvicorn.run(app, host="0.0.0.0", port=PROXY_PORT)
