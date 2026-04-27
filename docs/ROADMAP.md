# MMM Roadmap

Ideas and future directions not yet on the project board. Items here are candidates for future phases as the project matures. This is a living document — add here first, promote to the board when scope and timing are clear.

---

## Phase 3 — Management and Accessibility

### Installer Package / Tool
The current install.sh and install.ps1 scripts handle basic setup, but they are manual and bare. A proper installer would lower the barrier to adoption significantly and is important before MMM has a public user base.

Considerations:
- Guided setup flow: detect backend, set ports, generate initial .env
- Service registration (systemd, launchd, NixOS module, WinSW) handled automatically
- Validation step: confirm MMM can reach the configured backend before finishing
- Possibly pip-installable (`pip install mmm-proxy`) for Python-native environments
- Package manager targets: NixOS flake, Homebrew formula, AUR, apt/deb

The existing scripts are a starting point; the goal is a single command that leaves MMM fully running.

---

## Phase 4 — Ecosystem and Visibility

### MMM Web UI
A browser-based management interface served by MMM itself. Consolidates three related needs into one surface:

**Settings management** — Edit and apply .env configuration without touching the file directly. Fields for all env vars with descriptions, validation, and a save-and-reload action. Removes the need to SSH into the host to change a port or key.

**Character editor** — Create, edit, clone, and delete characters without writing JSON. Form fields map directly to the characters.json structure. Live preview of how behavior block values translate to backend parameters (e.g. creativity: high → temperature: 1.1). Save triggers a hot reload — no restart needed.

**Interactive parameter tuning / model playground** — Send test prompts to a character or raw model and adjust parameters on the fly. Sliders or dropdowns for temperature, top_p, context window, etc. Compare responses side-by-side before committing changes to the character definition. The goal is shortening the tuning loop — instead of editing JSON, restarting, and testing in a front-end, you tune and test in one place.

All three panels belong in the same UI because they share a workflow: adjust a setting, send a test prompt, see the result, decide if it's right.

Implementation notes:
- Thin FastAPI-served HTML/JS — no heavy frontend framework needed
- Auth-gated (admin role required)
- WebSocket or SSE for streaming playground responses
- Mobile-usable for quick on-the-fly adjustments

### Community Preset Repository
A public companion repo where the community shares character presets as self-contained characters.json entries. Would include a validation tool for linting presets, a tag taxonomy (tool-calling, conversational, reasoning, coding, creative, persona), backend compatibility tags, and testing guidelines.

Long-term could support a CLI command like `mmm pull community/nova-tool-caller`.

Gated on having at least two non-Ollama backends fully working — presets aren't portable until the backends are real.

---

## Phase 5 — Advanced Operations

### Preset Marketplace / Registry API
Extends the community repo into a versioned, hosted registry with pull-by-reference support in characters.json. Significant infrastructure lift (hosting, auth, CDN).

### Advanced Backend Routing and Load Balancing
Round-robin or least-loaded routing across multiple instances of the same backend type, with failover and GPU-first priority routing. Likely an evolution of Phase 2's multi-backend routing work rather than a separate effort.

### Performance Benchmarking Tools
Token throughput per preset, time-to-first-token distribution, quality regression hooks for comparing outputs before and after a preset change. Could surface in the Phase 4 Web UI playground.

### SSO / OAuth User Management
Extends the Phase 3 multi-user system to org identity providers with OIDC, group-based role assignment, and audit log enrichment.

### Nova Harness BI Lane Integration
Structured export of MMM's per-character token usage into the Nova Harness BI lane once Gate 3 is live. Webhook or push for real-time stats forwarding.

---

## Notes

- Promote items to the project board when there is a clear owner, a defined scope, and a phase timeline.
- Items that require external decisions or dependencies should get `needs-decision` or `external-dependency` labels when promoted.
- The community preset repo should not be created until at least two non-Ollama backends are fully implemented.
- The Web UI playground and benchmarking tools are related — consider building them in coordination.
- The installer should be completed before any public announcement or community push.
