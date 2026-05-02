#!/usr/bin/env bash
# ─────────────────────────────────────────────
# MMM ON — Enable character injection
# ─────────────────────────────────────────────
# Disables bypass mode. MMM resumes intercepting
# and injecting character configs.
#
# No service restarts. No port changes.
# Front-ends stay connected throughout.
#
# Usage: ./mmm-on.sh [host:port]
# ─────────────────────────────────────────────

MMM_URL="${1:-http://localhost:11434}"

echo "═══════════════════════════════════════════"
echo "  MMM ON — Make Modelfiles Matter"
echo "═══════════════════════════════════════════"

# Check if MMM is reachable
if ! curl -sf "$MMM_URL/mmm/bypass" > /dev/null 2>&1; then
    echo "  ERROR: MMM is not reachable at $MMM_URL"
    echo "  Is the service running?"
    exit 1
fi

# Check current state
CURRENT=$(curl -sf "$MMM_URL/mmm/bypass" | python3 -c "import sys,json; print(json.load(sys.stdin)['bypass'])" 2>/dev/null)

if [ "$CURRENT" = "False" ]; then
    echo "  MMM is already active."
    echo "  Character injection: ON"
    exit 0
fi

# Disable bypass
RESULT=$(curl -sf -X POST "$MMM_URL/mmm/bypass/off")
echo ""
echo "  $RESULT"
echo ""
echo "═══════════════════════════════════════════"
echo "  MMM is ON — character injection active"
echo "═══════════════════════════════════════════"
