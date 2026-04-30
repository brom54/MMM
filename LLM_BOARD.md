# LLM_BOARD — MMM

## Scope
Current focus = Phase 1. Read this before deeper repo search.

## Reality now
- MMM is in daily homelab use as the Ollama-facing consistency proxy.
- Proven: character injection, global defaults, bypass mode, heartbeat streaming.
- Auth code exists but needs end-to-end validation.
- vLLM and LM Studio backends are next live integration tests.
- Nova Harness Conductor integration pattern still needs formal docs.

## Phase 1 — Core stable
- `#1` Test and validate auth system — In Progress, P0, Auth.
- `#2` Test vLLM backend integration — In Progress, P1, Backends.
- `#3` Test LM Studio backend integration — In Progress, P1, Backends.
- `#4` Add .gitattributes — Done, P1, Core.
- `#5` Document Conductor integration pattern — Todo, P1, Integration.

Phase 1 done means auth is tested, at least one non-Ollama backend is validated, Conductor integration is documented, and LLM docs match the board.

## Later phases
- Phase 2: `#6` multi-backend routing, `#8` Ollama-to-vLLM mapping, `#9` Ollama-to-LM Studio mapping, `#10` cloud API backends.
- Phase 3: `#7` non-JSON character management, `#11` multi-user accounts, `#12` stats/audit reporting.

## Stop rule
Stop here unless a specific issue, backend file, or API endpoint requires deeper search.
