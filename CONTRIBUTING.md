# Contributing to MMM

Thanks for your interest in contributing! MMM is a focused tool with a clear architecture — contributions are welcome especially for Phase 2 backend implementations.

---

## The fastest way to contribute

**If you run LM Studio, llama.cpp, vLLM, or Kobold.cpp locally**, you can implement backend support in an afternoon. The architecture is already in place — you just fill in three methods. See [Implementing a Backend](#implementing-a-backend) below.

---

## Project structure

```
MMM/
├── proxy.py              — Main proxy, backend-agnostic orchestrator
├── modelfile_to_json.py  — Modelfile parser, generates characters.json
├── characters.json       — Character configuration (template)
├── requirements.txt      — Python dependencies
├── install.sh            — Linux/macOS installer
├── install.ps1           — Windows installer
├── backends/
│   ├── __init__.py       — Backend registry
│   ├── base.py           — Abstract base class (read this first)
│   ├── ollama.py         — Reference implementation (fully working)
│   ├── llamacpp.py       — Stub awaiting implementation
│   ├── lmstudio.py       — Stub awaiting implementation
│   ├── vllm.py           — Stub awaiting implementation
│   └── kobold.py         — Stub awaiting implementation
└── service/              — OS-specific service configs
```

---

## Implementing a Backend

Each backend lives in its own file in `backends/` and inherits from `BaseBackend`. Read `backends/base.py` first — every method is documented.

The three methods you **must** implement:

### 1. `translate_request(body, path) → (body, path)`

Converts an MMM/Ollama-format request into whatever format your backend expects.

**Input:** Ollama `/api/chat` body:
```json
{
  "model": "my-character",
  "messages": [
    {"role": "system", "content": "You are..."},
    {"role": "user", "content": "Hello"}
  ],
  "options": {"temperature": 0.7, "top_k": 20},
  "think": false,
  "stream": true
}
```

**For OpenAI-compatible backends** (llama.cpp, LM Studio, vLLM), translate to:
```json
{
  "model": "my-character",
  "messages": [
    {"role": "system", "content": "You are..."},
    {"role": "user", "content": "Hello"}
  ],
  "temperature": 0.7,
  "stream": true
}
```
And return path `v1/chat/completions` instead of `api/chat`.

**For Kobold**, you'll need to assemble messages into a single prompt string — see the notes in `backends/kobold.py`.

---

### 2. `translate_response_chunk(chunk) → bytes`

Converts a single streaming response chunk from your backend's format back to Ollama streaming format.

**Ollama streaming format** (what you need to output):
```json
{"model": "name", "created_at": "...", "message": {"role": "assistant", "content": "Hello"}, "done": false}
```

**OpenAI streaming format** (what llama.cpp/LM Studio/vLLM send):
```
data: {"id":"...","choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}
```

Strip the `data: ` prefix, parse the JSON, extract `choices[0].delta.content`, wrap in Ollama format.

---

### 3. `translate_response_full(body) → bytes`

Same as above but for non-streaming (complete) responses.

**Ollama complete format:**
```json
{"model": "name", "created_at": "...", "message": {"role": "assistant", "content": "Full response"}, "done": true, "done_reason": "stop"}
```

**OpenAI complete format:**
```json
{"choices": [{"message": {"role": "assistant", "content": "Full response"}, "finish_reason": "stop"}]}
```

---

### Testing your backend

1. Start your backend (llama.cpp server, LM Studio, etc.)
2. Start MMM pointing at it:
   ```bash
   BACKEND=llamacpp OLLAMA_HOST=http://localhost:8080 python3 proxy.py
   ```
3. Send a test request:
   ```bash
   # Test pass-through (no character injection)
   curl -s -X POST http://localhost:11435/api/chat \
     -H "Content-Type: application/json" \
     -d '{"model":"any-model","messages":[{"role":"user","content":"Hello"}],"stream":false}'

   # Test character injection (add a character to characters.json first)
   curl -s -X POST http://localhost:11435/api/chat \
     -H "Content-Type: application/json" \
     -d '{"model":"my-character","messages":[{"role":"user","content":"Hello"}],"stream":false}'
   ```
4. Verify:
   - Pass-through returns a normal response
   - Character injection returns a response in character
   - No thinking/reasoning leaks into the output
   - Streaming works (remove `"stream":false` and check token-by-token output)

---

## Adding a new backend that isn't listed

If you want to add support for a backend that doesn't have a stub yet (Jan, Cortex, Llamafile, etc.):

1. Create `backends/mybackend.py`
2. Inherit from `BaseBackend`
3. Implement all abstract methods
4. Add it to the `BACKENDS` dict in `backends/__init__.py`
5. Open a PR with a note about what you tested on

---

## Other ways to contribute

- **Characters:** Share interesting character prompts in Discussions
- **Bug reports:** Open an issue with the error, your OS, and backend version
- **Documentation:** Improve the README, add examples, fix typos
- **Testing:** Try MMM on a platform or front-end not yet tested and report results

---

## Pull request checklist

- [ ] Code runs without errors
- [ ] Tested manually against the actual backend
- [ ] Pass-through still works for unrecognized models
- [ ] No secrets or personal configs committed
- [ ] Updated README if adding a new backend

---

## Questions?

Open a Discussion on GitHub. No question is too basic.
