# MMM Roadmap

Ideas and future directions not yet on the project board. Items here are candidates for Phase 4 and Phase 5 as the project matures. This is a living document — add here first, promote to the board when scope and timing are clear.

---

## Phase 4 — Ecosystem and Visibility

### Community Preset Repository
A public companion repo (e.g. `brom54/MMM-presets` or a GitHub-hosted registry) where the community can share and discover character presets. Presets are self-contained characters.json entries anyone can drop into their own characters.json.

Considerations:
- Preset schema validation tool so contributed presets can be linted before submission
- Tag taxonomy: tool-calling, conversational, reasoning, coding, creative, persona
- Backend compatibility tags (ollama, vllm, lmstudio, openai)
- Preset testing guidelines — how to document what model family a preset was tuned for
- Could eventually be a separate CLI command: `mmm pull community/nova-tool-caller`

This becomes more valuable once MMM has a public user base and multiple backends are fully implemented.

### Web-Based Character Editor
A minimal browser UI (served by MMM itself or as a companion app) for creating and editing characters without touching JSON directly. Target users: people who want MMM's consistency guarantees but not JSON authoring.

Considerations:
- Likely a thin FastAPI-served HTML/JS page
- Form fields map to characters.json structure
- Live preview of translated parameters (behavior → temperature etc.)
- Saves back to characters.json and triggers a reload
- Not a priority while the Modelfile watcher covers the Ollama use case well

---

## Phase 5 — Advanced Operations

### Preset Marketplace / Registry API
A hosted registry where presets are versioned, rated, and discoverable via API. Extends the community repo concept into a more structured system.

- Versioned preset publishing with changelogs
- Pull-by-reference in characters.json: `{"$ref": "mmm://community/nova-tool-caller@1.2"}`
- Requires infrastructure (hosting, auth, CDN) — significant effort

### Advanced Backend Routing and Load Balancing
When multiple backend instances of the same type are available, route intelligently:
- Round-robin or least-loaded routing across Ollama instances
- Failover when a backend becomes unhealthy
- Priority routing — prefer GPU-backed instance, fall back to CPU

### Performance Benchmarking Tools
Tooling to measure and compare preset performance across backends:
- Token throughput per preset
- Time-to-first-token distribution
- Quality regression testing hooks (compare outputs before/after a preset change)

### SSO / OAuth User Management
Extend the multi-user system (Phase 3) to support organizational identity providers:
- OAuth 2.0 / OIDC integration
- Role assignment via identity provider groups
- Scoped API keys tied to SSO identities
- Audit log enriched with SSO identity attributes

### Nova Harness BI Lane Integration
Once the Nova Harness BI lane (Gate 3) is live, MMM's audit log becomes a data source:
- Structured export of per-character token usage for BI ingestion
- Webhook or push mechanism for real-time stats forwarding
- Dashboard presets for model usage and cost reporting

---

## Notes

- Promote items to the project board when there is a clear owner, a defined scope, and a phase timeline.
- Items that require external decisions or dependencies should get `needs-decision` or `external-dependency` labels when promoted.
- The community preset repo should not be created until at least two non-Ollama backends are fully implemented — the preset ecosystem is only useful when presets are genuinely backend-portable.
