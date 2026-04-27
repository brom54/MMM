#!/usr/bin/env python3
"""
MMM — Modelfile Directory Watcher
===================================
Watches the modelfiles/ directory for new or changed Modelfiles.
When a change is detected, runs modelfile_to_json.py to convert
and merge into characters.json, then signals the proxy to reload
its character config without a restart.

Usage:
    python3 watcher.py

Environment variables:
    MODELFILES_DIR      Directory to watch      (default: ./modelfiles)
    CONFIG_FILE         characters.json path    (default: ./characters.json)
    WATCH_INTERVAL      Poll interval seconds   (default: 5)

The watcher runs as a background thread inside the proxy process,
or can be run standalone for testing.

No external dependencies required — uses Python's built-in watchdog
via polling (no inotify/fsevents needed for cross-platform support).
"""

import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from threading import Thread

log = logging.getLogger("mmm.watcher")

MODELFILES_DIR  = Path(os.getenv("MODELFILES_DIR",  Path(__file__).parent / "modelfiles"))
CONFIG_FILE     = Path(os.getenv("CONFIG_FILE",     Path(__file__).parent / "characters.json"))
WATCH_INTERVAL  = float(os.getenv("WATCH_INTERVAL", "5"))
CONVERTER       = Path(__file__).parent / "modelfile_to_json.py"


def hash_directory(directory: Path) -> str:
    """
    Hash the contents of all Modelfiles in a directory.
    Returns a stable hash that changes when any file is added,
    removed, or modified.
    """
    hasher = hashlib.md5()
    try:
        for path in sorted(directory.iterdir()):
            if not path.is_file():
                continue
            name_lower = path.name.lower()
            is_modelfile = (
                name_lower.startswith("modelfile")
                or name_lower.endswith(".modelfile")
                or "." not in path.name
            )
            if not is_modelfile:
                continue
            hasher.update(path.name.encode())
            hasher.update(str(path.stat().st_mtime).encode())
            hasher.update(str(path.stat().st_size).encode())
    except Exception as e:
        log.warning(f"Could not hash directory: {e}")
    return hasher.hexdigest()


def run_converter() -> bool:
    """
    Run modelfile_to_json.py to convert Modelfiles to characters.json.
    Returns True on success, False on failure.
    """
    if not CONVERTER.exists():
        log.error(f"Converter not found: {CONVERTER}")
        return False

    try:
        result = subprocess.run(
            [sys.executable, str(CONVERTER), str(MODELFILES_DIR), str(CONFIG_FILE)],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            log.info("Modelfile conversion successful")
            if result.stdout:
                for line in result.stdout.strip().splitlines():
                    log.debug(f"  converter: {line}")
            return True
        else:
            log.error(f"Converter failed (exit {result.returncode})")
            if result.stderr:
                log.error(result.stderr.strip())
            return False
    except subprocess.TimeoutExpired:
        log.error("Converter timed out after 30s")
        return False
    except Exception as e:
        log.error(f"Could not run converter: {e}")
        return False


def reload_characters(characters_ref: dict | None = None) -> dict:
    """
    Reload characters.json and return the new character dict.
    If characters_ref is provided, updates it in-place.
    """
    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
        characters = data.get("characters", {})
        log.info(f"Reloaded {len(characters)} character(s): {', '.join(characters.keys())}")
        if characters_ref is not None:
            characters_ref.clear()
            characters_ref.update(characters)
        return characters
    except Exception as e:
        log.error(f"Could not reload {CONFIG_FILE}: {e}")
        return {}


class ModelfileWatcher:
    """
    Watches the modelfiles/ directory and triggers conversion + reload
    when changes are detected.

    Usage:
        watcher = ModelfileWatcher(characters_dict)
        watcher.start()   # starts background thread
        watcher.stop()    # stops the thread
    """

    def __init__(self, characters_ref: dict | None = None):
        """
        Args:
            characters_ref: The live CHARACTERS dict from proxy.py.
                           If provided, it will be updated in-place on reload.
                           If None, watcher runs conversion only.
        """
        self.characters_ref = characters_ref
        self._running       = False
        self._thread        = None
        self._last_hash     = None

    def start(self):
        """Start the background watcher thread."""
        if not MODELFILES_DIR.exists():
            log.warning(f"Modelfiles directory not found: {MODELFILES_DIR} — creating it")
            MODELFILES_DIR.mkdir(parents=True, exist_ok=True)

        # Run once on startup to pick up any Modelfiles already present
        self._check_and_convert(force=True)

        self._running = True
        self._thread  = Thread(target=self._watch_loop, daemon=True, name="mmm-watcher")
        self._thread.start()
        log.info(f"Watcher started — watching {MODELFILES_DIR} every {WATCH_INTERVAL}s")

    def stop(self):
        """Stop the background watcher thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        log.info("Watcher stopped")

    def _watch_loop(self):
        while self._running:
            try:
                self._check_and_convert()
            except Exception as e:
                log.error(f"Watcher error: {e}")
            time.sleep(WATCH_INTERVAL)

    def _check_and_convert(self, force: bool = False):
        """Check for changes and convert if needed."""
        if not MODELFILES_DIR.exists():
            return

        current_hash = hash_directory(MODELFILES_DIR)

        if force or current_hash != self._last_hash:
            if not force:
                log.info("Modelfile change detected — converting")
            self._last_hash = current_hash

            if run_converter():
                reload_characters(self.characters_ref)
            else:
                log.warning("Conversion failed — characters.json not updated")

    def trigger(self):
        """Manually trigger a conversion + reload. Used by /mmm/refresh endpoint."""
        log.info("Manual watcher trigger")
        self._check_and_convert(force=True)


# ─────────────────────────────────────────────
#  STANDALONE MODE
# ─────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    log.info("MMM Modelfile Watcher — standalone mode")
    log.info(f"Watching: {MODELFILES_DIR}")
    log.info(f"Config:   {CONFIG_FILE}")
    log.info(f"Interval: {WATCH_INTERVAL}s")
    log.info("Press Ctrl+C to stop")

    watcher = ModelfileWatcher()
    watcher.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watcher.stop()
        log.info("Stopped")
