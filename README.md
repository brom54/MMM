# MMM — Make Modelfiles Matter

A universal AI consistency proxy. Define your agent once — personality, parameters, response style, behavior — and MMM enforces that definition across every model, every provider, and every front-end.

## The Problem

Every AI front-end (Open WebUI, OpenClaw, Discord bots, n8n, LangGraph) overrides your model's personality and parameters with its own defaults. You spend time crafting a perfect Modelfile or character config, then the front-end ignores it. MMM sits between your front-ends and your inference backends, intercepting requests and injecting your character definitions before they reach the model.

## What MMM Does

- **Injects character system prompts** — your personality definition overrides whatever the front-end sends
- **Enforces parameters** — temperature, context window, response length, repeat penalty, all locked to your config
- **Applies global defaults** — non-character models get sane defaults (context window, response cap) automatically
- **Heartbeat keepalive** — prevents front-end timeouts during slow inference on large models
- **Translates between backends** — same character works across Ollama, llama.cpp, LM Studio (Phase 2)
- **Bypass mode** — instantly toggle injection on/off without restarting anything
- **Tracks stats silently** — token counts, timing, prompt delta, per-character aggregates
- **Audit logging** — every request attributed to an API key identity, stored in SQLite
- **API key management** — generate, revoke, rotate keys via HTTP endpoints

## Quick Start

### Prerequisites

- Python 3.10+
- An inference backend (Ollama, llama.cpp, LM Studio)
- A front-end that speaks the Ollama API (Open WebUI, OpenClaw, etc.)

### Install

```bash
git clone https://github.com/geraldbromley/MMM.git
cd MMM
pip install -r requirements.txt
cp .env.example .env
```

### Configure

Edit `.env`:

```bash
# MMM listens here — point your front-ends at this port
PROXY_PORT=11434

# Your inference backend
OLLAMA_HOST=http://localhost:11435
BACKEND=ollama

# Security — change this
MMM_API_KEY=your-secret-key-here
```

If running Ollama, move it to a different port so MMM can take the default:

- **NixOS:** Set `port = 11435;` in your Ollama service config
- **Linux/macOS:** Set `OLLAMA_HOST=0.0.0.0:11435` in Ollama's environment
- **Windows:** Set the environment variable before starting Ollama

### Add a Character

Edit `characters.json`:

```json
{
  "defaults": {
    "parameters": {
      "num_ctx": 65536,
      "num_predict": 2048
    }
  },
  "characters": {
    "my-agent": {
      "description": "My custom AI agent",
      "think": false,
      "base_model": "qwen3:32b",
      "parameters": {
        "temperature": 0.7,
        "top_p": 0.85,
        "num_ctx": 65536,
        "num_predict": 2048
      },
      "system_prompt": "You are my custom agent. [Your personality and instructions here.]"
    }
  }
}
```

Or drop an existing Ollama Modelfile into the `modelfiles/` directory — MMM auto-converts it.

### Run

```bash
python3 proxy.py
```

Select your character's model name in your front-end. MMM intercepts the request, strips the front-end's system prompt, injects yours, applies your parameters, and forwards to the backend.

### Install as a Service

**Linux (systemd):**
```bash
sudo cp service/ollama-character-proxy.service /etc/systemd/system/
sudo systemctl enable ollama-character-proxy
sudo systemctl start ollama-character-proxy
```

**macOS (launchd):**
```bash
cp service/com.mmm.proxy.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.mmm.proxy.plist
```

**NixOS:** See `service/nixos-module.nix` for a complete NixOS module.

**Windows:** See `service/mmm-service.xml` for WinSW configuration.

## Configuration

### characters.json

Characters are defined in `characters.json`. Each character has a key (the model name your front-end requests), a base model (what actually runs), parameters, and a system prompt.

**Priority order for parameters:**
1. Character-specific parameters — highest, always wins
2. Global defaults — applies to non-character models
3. Backend defaults — lowest, only if nothing else is set

**Defaults block** — applies to all non-character pass-through models:

```json
{
  "defaults": {
    "parameters": {
      "num_ctx": 65536,
      "num_predict": 2048,
      "num_keep": 2048,
      "num_batch": 4096
    }
  }
}
```

**Behavior block** (optional) — semantic intent that auto-translates to backend-specific parameters:

```json
"behavior": {
  "creativity": "high",
  "response_length": "medium",
  "formality": "casual",
  "reasoning": false
}
```

Values: `creativity` (very_low/low/medium/high/very_high), `response_length` (brief/short/medium/long/very_long), `formality` (very_formal/formal/neutral/casual/very_casual), `reasoning` (true/false).

**Legacy format** — top-level `parameters` block still works and always will:

```json
"my-character": {
  "base_model": "qwen3:32b",
  "parameters": {"temperature": 0.7},
  "system_prompt": "You are..."
}
```

### Modelfile Ingest

Drop Ollama Modelfiles into the `modelfiles/` directory. MMM auto-converts them to `characters.json` entries and reloads. Existing Modelfiles work unchanged.

### Environment Variables

See `.env.example` for all options. Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `PROXY_PORT` | `11435` | Port MMM listens on |
| `OLLAMA_HOST` | `http://localhost:11434` | Backend URL |
| `BACKEND` | `ollama` | Backend type |
| `MMM_API_KEY` | `CHANGE_ME` | API key for inbound auth |
| `MMM_ALLOWED_IPS` | (empty) | IP allowlist (CIDR supported) |
| `HEARTBEAT_INTERVAL` | `3` | Seconds between keepalive pings |
| `MODEL_REFRESH_HOURS` | `6` | Hours between model cache refresh |

### Parameter Reference

| Parameter | Description | Range | Good defaults |
|-----------|-------------|-------|---------------|
| `num_ctx` | Context window size. Total tokens the model can see — includes system prompt, conversation history, and response. Controls VRAM allocation. | 2048-262144 | 32768-65536 |
| `num_predict` | Max tokens the model will generate per response. Included in the num_ctx budget. | 1 to unlimited | 1024-2048 |
| `temperature` | Controls randomness. Lower is more focused and deterministic, higher is more creative and varied. | 0.0-2.0 | 0.4 (agentic), 0.7 (chat) |
| `top_p` | Nucleus sampling. Controls how many token options the model considers by probability mass. | 0.0-1.0 | 0.8-0.95 |
| `top_k` | Limits token selection to the top K most likely tokens. | 1-100+ | 20-40 |
| `repeat_penalty` | Penalizes repetition. Higher values discourage repeated words and phrases. | 1.0-2.0 | 1.1 (agentic), 1.5 (chat) |
| `num_keep` | Number of tokens from the start of context that are never dropped. Protects your system prompt from being pushed out by long conversations. | 0+ | Match your system prompt length |
| `num_batch` | Tokens processed per step during prompt evaluation. Higher is faster prefill but uses more peak memory. | 128-8192+ | 4096 |

## API Endpoints

### Admin

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/mmm/status` | GET | Health, cache, stats, bypass state |
| `/mmm/refresh` | POST | Refresh model cache |
| `/mmm/models` | GET | List cached models |
| `/mmm/bypass` | GET | Check bypass mode |
| `/mmm/bypass/on` | POST | Enable bypass (transparent proxy) |
| `/mmm/bypass/off` | POST | Disable bypass (injection active) |

### Key Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/mmm/keys/generate` | POST | Create a new API key (returned once) |
| `/mmm/keys` | GET | List identities (no key values) |
| `/mmm/keys/{id}/revoke` | POST | Revoke a key immediately |
| `/mmm/keys/{id}/rotate` | POST | Generate new key for existing identity |
| `/mmm/audit` | GET | Query request audit log |

### Toggle Scripts

```bash
# Disable character injection (bypass mode)
./mmm-off.sh

# Re-enable character injection
./mmm-on.sh

# Use against a remote MMM instance
./mmm-on.sh http://10.0.0.11:11434
```

No service restart, no port change, no front-end reconfiguration needed.

## Architecture

```
Front-ends (Open WebUI, OpenClaw, n8n, Discord, etc.)
                    |
          MMM Proxy (port 11434)
          |-- Character injection
          |-- Parameter enforcement
          |-- Global defaults
          |-- Heartbeat keepalive
          |-- Auth / audit
          |-- Stats collection
                    |
    Inference Backends (Ollama, llama.cpp, LM Studio, etc.)
```

MMM is transparent to front-ends — they see a standard Ollama-compatible API. Models not defined in `characters.json` pass through untouched with global defaults applied.

## Security

- **API keys** are hashed (SHA-256) in the database — plain keys are returned once on generation and never stored
- **Master key** (`MMM_API_KEY` in `.env`) works as a bootstrap and emergency override, never written to the database
- **IP allowlist** (`MMM_ALLOWED_IPS`) restricts access by source IP or CIDR range
- **`.env` and `mmm.db`** are in `.gitignore` — never committed to version control
- We recommend storing `MMM_API_KEY` in your OS keychain or secrets manager rather than in plaintext

## Roadmap

| Phase | Status | Work |
|-------|--------|------|
| 1 | Done | Ollama proxy, character injection, heartbeat, stats, auth, bypass mode, defaults |
| 2 | Next | llama.cpp and LM Studio backends, tool call format translation |
| 2.5 | Planned | Cloud provider support (OpenAI, Anthropic, Groq), keyring/encrypted secrets |
| 3 | Planned | Tiered defaults by model size, dev/debug mode, Modelfile format converters |
| 4 | Planned | CLI tool, PyPI package, admin WebUI, local user accounts |
| 5 | Planned | GUI installer, community character/agent library, OAuth2/SSO |

## License

MIT — see [LICENSE](LICENSE).

## Credits

Created by Gerald Bromley. Built with FastAPI, httpx, and SQLite.
