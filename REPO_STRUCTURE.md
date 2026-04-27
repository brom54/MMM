# MMM — GitHub Repository Structure

## Directory Layout

```
MMM/
├── README.md                        # Project overview, quick start, full docs
├── LICENSE                          # MIT License
├── CONTRIBUTING.md                  # How to contribute
├── llms.txt                         # LLM-friendly project description
├── .gitignore                       # Protects .env, mmm.db, secrets
├── .env.example                     # Environment variable template
├── requirements.txt                 # Python dependencies
│
├── proxy.py                         # Main proxy server
├── router.py                        # Backend routing and stats
├── behavior.py                      # Semantic behavior translation
├── auth.py                          # Authentication middleware
├── database.py                      # SQLite identity and audit layer
├── secrets_provider.py              # Outbound API key management
├── modelfile_to_json.py             # Modelfile → JSON converter
├── watcher.py                       # Modelfile directory watcher
├── characters.json                  # Character configs and defaults
│
├── mmm-on.sh                        # Enable injection (bypass off)
├── mmm-off.sh                       # Disable injection (bypass on)
├── install.sh                       # Linux/macOS installer
├── install.ps1                      # Windows installer
│
├── backends/                        # Backend translation modules
│   ├── __init__.py                  # Registry — get_backend(), list_backends()
│   ├── base.py                      # Abstract BaseBackend class
│   ├── ollama.py                    # Ollama (fully implemented)
│   ├── llamacpp.py                  # llama.cpp (Phase 2 stub)
│   ├── lmstudio.py                  # LM Studio (Phase 2 stub)
│   ├── vllm.py                      # vLLM (Phase 2 stub)
│   ├── kobold.py                    # KoboldCpp (Phase 2 stub)
│   └── mlx.py                       # MLX (Phase 2 stub)
│
├── service/                         # Platform service configs
│   ├── ollama-character-proxy.service  # systemd (Linux)
│   ├── com.mmm.proxy.plist             # launchd (macOS)
│   ├── mmm-service.xml                 # WinSW (Windows)
│   └── nixos-module.nix               # NixOS module
│
├── modelfiles/                      # Drop Ollama Modelfiles here
│   └── .gitkeep                     # Keeps empty dir in git
│
└── examples/                        # Example configs and characters
    ├── characters-minimal.json      # Minimal single-character example
    ├── characters-agentic.json      # Agentic character with tool instructions
    ├── characters-multi.json        # Multiple characters example
    └── Modelfile.example            # Example Ollama Modelfile
```

## What Goes Where

### Root directory — core application
All Python source files live at the root. No `src/` subdirectory. This keeps
imports simple (`from router import BackendRouter`) and matches how the
application runs on the server (`python3 proxy.py` from the install directory).

### backends/ — one file per backend
Each backend is a self-contained module that implements the BaseBackend
interface. Adding a new backend means adding one file here and registering
it in __init__.py. No other files need to change.

### service/ — platform service configs
Users copy the appropriate file for their platform. These are reference
configs, not auto-installed. The install scripts handle copying them.

### modelfiles/ — user's Modelfiles
Users drop their existing Ollama Modelfiles here. The watcher auto-converts
them to characters.json entries. This directory ships empty with a .gitkeep.

### examples/ — reference configurations
Example characters.json files showing different use cases. Users copy and
modify these rather than editing the main characters.json from scratch.

## Files NOT in the repo (generated at runtime)

```
.env                    # User's actual config (copied from .env.example)
mmm.db                  # SQLite database (created on first run)
ollama-port.env         # Port config for toggle scripts (created by mmm-on.sh)
__pycache__/            # Python bytecode cache
```

## Clone and Run

```bash
git clone https://github.com/geraldbromley/MMM.git
cd MMM
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your settings
python3 proxy.py
```

The repo structure is designed so that cloning and running requires
no directory reorganization. The install location on the server
mirrors the repo layout exactly.
