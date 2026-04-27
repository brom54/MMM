# LLM_BOARD — MMM (Make Modelfiles Matter)

## Scope

- Current phase focus = Phase 1
- Read this before deeper repo search.

## Reality Now

- Core proxy is deployed and in daily use on the homelab NixOS inference machine
- Ollama is the only active backend; MMM proxies it on port 11434, Ollama listens on 11435
- Two characters defined and in use (ash-agent, ash-qwen3)
- Bypass mode, global defaults, character injection, heartbeat — all proven in production
- Auth system (database.py, auth.py) is implemented but untested — MMM_API_KEY is currently blank
- vLLM and LM Studio backends are stubs; Sam has instances ready to test
- Nova Harness Conductor integration pattern not yet formally documented

## Phase 1

### Active / In Progress

- `#1` open, todo — Test and validate auth system (P0, Area: Auth)
- `#2` open, todo — Test vLLM backend integration (P1, Area: Backends)
- `#3` open, todo — Test LM Studio backend integration (P1, Area: Backends)
- `#4` open, todo — Add .gitattributes for cross-platform line endings (P1, Area: Core)
- `#5` open, todo — Document Conductor integration pattern (P1, Area: Integration)

### Phase 1 Definition of Done

- Auth tested end-to-end: key generation, enforcement, revocation, rotation
- At least one non-Ollama backend validated against a live instance
- Conductor integration pattern documented in docs/
- LLM files current and accurate
- .gitattributes in place

## Phase 2

- `#6` open, todo — Multi-backend routing (Area: Core, needs-design)
- `#7` open, todo — Non-JSON character management for non-Ollama backends (Area: Characters/Config, needs-design)
- `#8` open, todo — Implement full vLLM parameter mapping (Area: Backends)
- `#9` open, todo — Implement full LM Studio parameter mapping (Area: Backends)
- `#10` open, todo — Cloud API backends — OpenAI and Anthropic (Area: Backends, needs-research)

## Phase 3

- `#11` open, todo — Multi-user account system (Area: Auth, needs-design)
- `#12` open, todo — Stats and audit reporting surface (Area: Stats/Audit, needs-design)

## Phase 4 / Phase 5

- See `docs/ROADMAP.md` for items not yet on the board.

## Next

- Start with `#1` (auth) — it is the only untested production-critical system
- `#2` and `#3` can run in parallel once auth is settled
- `#5` (Conductor integration doc) is high priority for Nova Harness alignment

## Stop Rule

Stop here unless a specific file, issue, or implementation question requires deeper search.
