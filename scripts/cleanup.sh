#!/usr/bin/env bash
# scripts/cleanup.sh — Sprint 1 cleanup
# Removes: nested duplicate folder, literal-name folder, stub files
# Usage: bash scripts/cleanup.sh
set -e
REPO_ROOT="${1:-.}"
cd "$REPO_ROOT"

echo "=== MacroRegime Cleanup v2 ==="

# 1. Remove nested duplicate macroregime/macroregime/
if [ -d "macroregime/macroregime" ]; then
    echo "Removing nested duplicate folder..."
    rm -rf macroregime/macroregime
fi
if [ -d "macroregime" ] && [ "$(ls -A macroregime 2>/dev/null)" ]; then
    # If macroregime/ has the SAME content as root (full repo dupe), warn
    if [ -f "macroregime/app.py" ] && [ -f "app.py" ]; then
        if [ "$(stat -c%s macroregime/app.py 2>/dev/null || stat -f%z macroregime/app.py)" = "$(stat -c%s app.py 2>/dev/null || stat -f%z app.py)" ]; then
            echo "Removing duplicate macroregime/ folder (matches root)..."
            rm -rf macroregime/
        fi
    fi
fi

# 2. Remove literal-named bad folder from botched mkdir
if [ -d "{config,data,engines,ui" ]; then
    echo "Removing bad-mkdir literal folder..."
    rm -rf "{config,data,engines,ui"
fi
if [ -d "{config,data,engines,ui}" ]; then
    rm -rf "{config,data,engines,ui}"
fi

# 3. Replace stub engines (zero functionality)
echo "Tagging stub files for replacement..."
for stub in engines/edgar_scraper_engine.py engines/supply_chain_graph_engine.py engines/transition_engine.py engines/playbook_engine.py engines/risk_range_engine.py engines/greeks_proxy_vanna_charm_EXTENSION.py; do
    if [ -f "$stub" ]; then
        # Verify it's truly a stub (small file)
        size=$(wc -c < "$stub")
        if [ "$size" -lt 800 ]; then
            mv "$stub" "${stub}.OLD_STUB"
            echo "  Renamed $stub → ${stub}.OLD_STUB"
        fi
    fi
done

# 4. Clear .pyc cache
echo "Clearing pycache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true

# 5. Remove .cache snapshot (force fresh build with new engines)
if [ -d ".cache" ]; then
    echo "Clearing snapshot cache (forces fresh build)..."
    rm -rf .cache/snapshot.pkl .cache/snapshot_v3.pkl .cache/snapshot_v3.json 2>/dev/null || true
fi

echo ""
echo "=== Cleanup Complete ==="
echo "Next: drop the new v2 files into engines/, data/, config/"
echo "Then: streamlit run app.py"
