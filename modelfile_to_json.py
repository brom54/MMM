#!/usr/bin/env python3
"""
MMM — Make Modelfiles Matter
modelfile_to_json.py
====================
Scans a directory for Modelfiles, parses them, and generates/updates
characters.json for the MMM proxy.

Usage:
    python3 modelfile_to_json.py [modelfiles_dir] [output_json]

Defaults:
    modelfiles_dir : ./modelfiles
    output_json    : ./characters.json

Modelfile naming convention:
    The filename (without extension) becomes the character key.
    Examples:
        modelfiles/ash-williams         → key: "ash-williams"
        modelfiles/Modelfile.ash        → key: "ash"
        modelfiles/Modelfile            → skipped (no character name)
"""

import json
import logging
import re
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("modelfile-parser")

KNOWN_PARAMS = {
    "temperature":    float,
    "top_p":          float,
    "top_k":          int,
    "repeat_penalty": float,
    "num_ctx":        int,
    "num_predict":    int,
    "repeat_last_n":  int,
}

def parse_modelfile(path: Path) -> dict | None:
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        log.warning(f"Could not read {path}: {e}")
        return None

    result = {
        "description":   f"Parsed from {path.name}",
        "think":         False,
        "base_model":    None,
        "parameters":    {},
        "system_prompt": ""
    }

    from_match = re.search(r"^\s*FROM\s+(\S+)", content, re.MULTILINE | re.IGNORECASE)
    if from_match:
        result["base_model"] = from_match.group(1).strip()

    for param_name, cast in KNOWN_PARAMS.items():
        pattern = rf"^\s*PARAMETER\s+{param_name}\s+(\S+)"
        match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
        if match:
            try:
                result["parameters"][param_name] = cast(match.group(1))
            except ValueError:
                log.warning(f"  Could not cast {param_name} — skipping")

    triple_match = re.search(r'^\s*SYSTEM\s+"""(.*?)"""', content, re.MULTILINE | re.DOTALL | re.IGNORECASE)
    if triple_match:
        result["system_prompt"] = triple_match.group(1).strip()
    else:
        single_match = re.search(r'^\s*SYSTEM\s+"([^"]*)"', content, re.MULTILINE | re.IGNORECASE)
        if single_match:
            result["system_prompt"] = single_match.group(1).strip()

    if not result["base_model"]:
        log.warning(f"  No FROM directive in {path.name} — skipping")
        return None

    return result

def derive_key(path: Path) -> str | None:
    name = path.stem
    for ext in (".modelfile", ".txt", ".json"):
        if name.lower().endswith(ext):
            name = name[:-len(ext)]
    for prefix in ("modelfile.", "modelfile-", "modelfile_"):
        if name.lower().startswith(prefix):
            name = name[len(prefix):]
            break
    if not name or name.lower() == "modelfile":
        return None
    return name.lower()

def scan_modelfiles(modelfiles_dir: Path) -> dict:
    if not modelfiles_dir.exists():
        log.error(f"Directory not found: {modelfiles_dir}")
        return {}

    characters = {}
    for path in sorted(modelfiles_dir.iterdir()):
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

        key = derive_key(path)
        if not key:
            log.info(f"Skipping {path.name} — no character name derivable")
            continue

        log.info(f"Parsing {path.name} → key: '{key}'")
        parsed = parse_modelfile(path)
        if parsed:
            characters[key] = parsed
            log.info(f"  ✓ base_model: {parsed['base_model']}, params: {len(parsed['parameters'])}, prompt: {len(parsed['system_prompt'])} chars")
        else:
            log.warning(f"  ✗ Could not parse {path.name}")

    return characters

def merge_with_existing(new_characters: dict, existing_path: Path) -> dict:
    if not existing_path.exists():
        return new_characters
    try:
        with open(existing_path) as f:
            existing = json.load(f)
        merged = dict(existing.get("characters", {}))
    except Exception as e:
        log.warning(f"Could not read existing {existing_path}: {e} — will overwrite")
        return new_characters

    for key, value in new_characters.items():
        action = "Updating" if key in merged else "Adding"
        log.info(f"{action}: '{key}'")
        merged[key] = value

    return merged

def main():
    modelfiles_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("./modelfiles")
    output_json    = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("./characters.json")

    log.info(f"Scanning: {modelfiles_dir.resolve()}")
    log.info(f"Output:   {output_json.resolve()}")

    new_characters = scan_modelfiles(modelfiles_dir)
    if not new_characters:
        log.warning("No characters parsed. characters.json not modified.")
        return

    merged = merge_with_existing(new_characters, output_json)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump({"characters": merged}, f, indent=2, ensure_ascii=False)

    log.info(f"Wrote {len(merged)} character(s) to {output_json}")

if __name__ == "__main__":
    main()
