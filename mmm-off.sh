#!/usr/bin/env bash
# ─────────────────────────────────────────────
# MMM OFF — Disable character injection
# ─────────────────────────────────────────────
# Enables bypass mode. MMM becomes a transparent
# proxy — all requests pass through untouched.
#
# No service restarts. No port changes.
# Front-ends stay connected throughout.
#
# Usage: ./mmm-off.sh [host:port]
# ─────────────────────────────────────────────

MMM_URL="${1:-http://localhost:11434}"

echo "═══════════════════════════════════════════"
echo "  MMM OFF — Bypass mode"
echo "═══════════════════════════════════════════"

# Check if MMM is reachable
if ! curl -sf "$MMM_URL/mmm/bypass" > /dev/null 2>&1; then
    echo "  ERROR: MMM is not reachable at $MMM_URL"
    echo "  Is the service running?"
    exit 1
fi

# Check current state
CURRENT=$(curl -sf "$MMM_URL/mmm/bypass" | python3 -c "import sys,json; print(json.load(sys.stdin)['bypass'])" 2>/dev/null)

if [ "$CURRENT" = "True" ]; then
    echo "  MMM is already in bypass mode."
    echo "  Character injection: OFF"
    exit 0
fi

# Enable bypass
RESULT=$(curl -sf -X POST "$MMM_URL/mmm/bypass/on")
echo ""
echo "  $RESULT"
echo ""
echo "═══════════════════════════════════════════"
echo "  MMM is OFF — transparent proxy only"
echo "  No injection, no stripping, no heartbeat"
echo "═══════════════════════════════════════════"
