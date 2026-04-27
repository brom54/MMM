# LLM_CONTEXT — MMM (Make Modelfiles Matter)

## Project

MMM is a universal AI inference consistency proxy written in Python with FastAPI. It sits between AI front-ends (Open WebUI, n8n, Discord bots, LangGraph agents, the Nova Harness Conductor) and inference backends (Ollama, llama.cpp, LM Studio, vLLM, cloud APIs). MMM intercepts requests, strips the front-end's system prompt, injects the configured character (system prompt + parameters + behavior), and forwards to the backend. Responses stream back through MMM with optional heartbeat keepalive.

## Why It Exists

MMM is not just a personality layer. It is a **managed inference contract system**. Front-ends and orchestrators should not need to know how to configure a model for tool-calling, creative response, reasoning, or any other task type. They select a named preset. MMM guarantees the model is configured correctly for that task — parameters, system prompt shape, and behavior semantics — regardless of which front-end or backend is in play.

Ollama Modelfiles define this perfectly for Ollama users, but every front-end overrides them. MMM solves this by being the single source of truth for how any model should behave.

## Core Concepts

**CHARACTER:** A named inference preset in characters.json. Contains a system prompt, parameters, and optional behavior block. When a front-end requests a model matching a character key, MMM intercepts and injects the full config. Unknown models pass through untouched (subject to global defaults).

**DEFAULTS:** A global parameter block in characters.json applied to all non-character models. Primary use: fixing backend defaults that would otherwise silently degrade inference (e.g. Ollama's 4k context window).

**BYPASS MODE:** Runtime toggle that makes MMM a transparent proxy — no injection, no character matching, no defaults. Toggle via POST /mmm/bypass/on and /mmm/bypass/off. No restart needed.

**BEHAVIOR BLOCK:** Optional semantic fields (creativity, response_length, formality, reasoning) that auto-translate to backend-specific parameters. Callers describe intent; MMM translates to temperature, max_tokens, etc.

**HEARTBEAT:** Zero-width space tokens sent while waiting for the backend to respond. Prevents front-end timeout errors on slow or large models.

## Architecture

```
Front-end / Orchestrator
        │
        ▼  (port 11434 default, configurable)
      [MMM]
        │  character match → inject system prompt + parameters
        │  no match → apply global defaults
        ▼  (port 11435 default, configurable)
  Inference Backend (Ollama, vLLM, LM Studio, etc.)
```

Request flow:
1. Front-end sends request
2. MMM checks character match against model name
3. If match: strip front-end system prompt, inject character system prompt + parameters
4. If no match: apply global defaults
5. Forward to backend
6. Stream response back with heartbeat keepalive

MMM is stateless per-request. All config lives in characters.json and .env.

## Nova Harness Integration

MMM is a named infrastructure component in the Nova Harness platform, alongside Ollama, n8n, and Zulip. It occupies the inference layer between the Conductor (orchestrator) and the backend.

The Conductor consciously selects inference presets by choosing which model name to request. Lane routing determines the preset:
- Tool-calling lane → request `nova-tool-caller` → MMM injects tight, deterministic parameters
- Conversational lane → request `nova-conversational` → MMM injects warm, flexible parameters
- Reasoning lane → request `nova-reasoning` → MMM enables thinking tokens and wider context

Nova-specific preset definitions live in the nova-harness repo (loaded via CONFIG_FILE env var). MMM core has no Nova-specific config baked in.

## File Structure

```
proxy.py              Main FastAPI server. Request interception, character injection,
                      heartbeat, bypass mode, admin endpoints, key management.
router.py             Backend routing, health checks, model cache, stats collection.
behavior.py           Semantic behavior → backend parameter translation.
auth.py               Inbound auth middleware. API key validation, IP allowlist, RequestContext.
database.py           SQLite layer. Identity/key management and persistent audit logging.
secrets_provider.py   Outbound API key management for cloud providers.
modelfile_to_json.py  Converts Ollama Modelfiles to characters.json entries.
watcher.py            Watches modelfiles/ for changes. Auto-converts and reloads.
characters.json       Character definitions, global defaults, behavior blocks.

backends/
  __init__.py         Backend registry. Maps names to classes.
  base.py             Abstract BaseBackend. All backends implement this interface.
  ollama.py           Ollama backend — fully implemented, reference implementation.
  vllm.py             vLLM backend — stub, implementation in progress (Phase 1).
  lmstudio.py         LM Studio backend — stub, implementation in progress (Phase 1).
  llamacpp.py         llama.cpp backend — stub.
  kobold.py           KoboldCpp backend — stub.
  mlx.py              MLX backend — stub.

service/              systemd, launchd, WinSW, and NixOS service configs.
examples/             Example Modelfiles and characters.json configs.
modelfiles/           Drop Modelfiles here; watcher auto-converts and reloads.
docs/                 Architecture, integration specs, roadmap.
```

## characters.json Schema

```json
{
  "defaults": {
    "parameters": {
      "num_ctx": 65536,
      "num_predict": 2048
    }
  },
  "characters": {
    "character-name": {
      "description": "Human-readable description",
      "think": false,
      "behavior": {
        "creativity": "low|medium|high|very_high",
        "response_length": "short|medium|long|unlimited",
        "formality": "casual|neutral|formal",
        "reasoning": false
      },
      "system_prompt": "...",
      "backends": {
        "ollama": {
          "base_model": "qwen3:32b",
          "parameters": {
            "temperature": 0.7,
            "top_p": 0.8,
            "num_ctx": 32768,
            "num_predict": 2048
          }
        }
      }
    }
  }
}
```

All fields are optional. Legacy top-level `parameters` blocks are supported alongside the new `behavior`/`backends` schema.

## API Endpoints

```
GET  /mmm/status              Health, backend state, model cache, per-character stats, bypass state, defaults
POST /mmm/refresh             Refresh model cache and rescan modelfiles/
GET  /mmm/models              List cached models
GET  /mmm/bypass              Check bypass state
POST /mmm/bypass/on           Enable bypass (transparent proxy, no injection)
POST /mmm/bypass/off          Disable bypass (injection active)
POST /mmm/keys/generate       Create new API key. Body: {"label":"name","type":"service|user","role":"user|admin"}
GET  /mmm/keys                List identities (metadata only, never key values)
POST /mmm/keys/{id}/revoke    Deactivate a key immediately
POST /mmm/keys/{id}/rotate    Generate new key, old key immediately invalid
GET  /mmm/audit               Query persistent request log. Filters: identity_id, character, limit
```

## Configuration

Environment variables loaded from .env:

```
PROXY_PORT            Port MMM listens on                    (default: 11434)
OLLAMA_HOST           Backend URL                            (default: http://localhost:11435)
BACKEND               Backend type                           (default: ollama)
CONFIG_FILE           Path to characters.json               (default: ./characters.json)
MMM_API_KEY           Inbound auth key. Empty disables auth  (default: CHANGE_ME)
MMM_ALLOWED_IPS       Comma-separated IP/CIDR allowlist      (default: empty = allow all)
HEARTBEAT_INTERVAL    Seconds between keepalive pings        (default: 3)
MODEL_REFRESH_HOURS   Hours between model cache auto-refresh (default: 6, 0=never)
MMM_DB_PATH           SQLite database path                   (default: ./mmm.db)
```

## Auth System

Inbound auth checks API keys against SQLite. Keys are stored as SHA-256 hashes — plain keys are returned once on generation and never stored. The identities table is forward-compatible with full user accounts (username, password_hash, email columns exist but are nullable until Phase 3).

MMM_API_KEY in .env acts as a master bootstrap key on first run. After that, manage keys via the /mmm/keys endpoints.

## Development Standards

- All character config fields are optional. Existing configs never break on update.
- Legacy parameters blocks are supported forever alongside the new behavior/backends schema.
- Backend stubs follow the BaseBackend interface in backends/base.py.
- Stats collection is silent — data accumulates in memory and SQLite but nothing surfaces unless queried.
- Bypass mode is a runtime toggle, not a restart. Front-ends stay connected.
- Global defaults apply to non-character models only. Character configs always take priority.
- Nova-specific presets do not belong in this repo. They live in nova-harness.

## Naming Conventions

Character keys in characters.json use kebab-case and should describe the task type or persona, not the underlying model:
- `nova-tool-caller` not `qwen3-tool`
- `nova-conversational` not `gemma4-chat`
- `ash-agent` not `ash-qwen3-32b`

Backend names match the keys in backends/__init__.py: `ollama`, `vllm`, `lmstudio`, `llamacpp`, `kobold`, `mlx`.

## Phase Model

| Phase | Focus |
|-------|-------|
| Phase 1 | Core stable — auth validated, first non-Ollama backends tested, Conductor integration documented |
| Phase 2 | Expanded capabilities — multi-backend routing, non-JSON character management, cloud API backends |
| Phase 3 | Advanced features — multi-user accounts, stats reporting surface, full backend parity |
| Phase 4 | Future — ideas under consideration, not yet scoped |
| Phase 5 | Long horizon — community, ecosystem, advanced operations |

## Next

Read `LLM_BOARD.md` for current issue state, active work, and next-step orientation.
