#!/usr/bin/env bash
# PatchGuard Demo Script
# Demonstrates the full Tier 0 pipeline: isolation, artifacts, replay.
# Requires: Python 3.12+, Docker, git

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
step() { echo -e "\n${YELLOW}=== $* ===${NC}"; }

step "PatchGuard Demo"
info "Verifying environment..."

# Check prerequisites
command -v python3.12 >/dev/null 2>&1 || { warn "python3.12 not found"; exit 1; }
command -v git >/dev/null 2>&1 || { warn "git not found"; exit 1; }
command -v docker >/dev/null 2>&1 || { warn "docker not found (needed for sandbox)"; exit 1; }
docker info >/dev/null 2>&1 || { warn "docker daemon not running"; exit 1; }

# Ensure Docker image exists
if ! docker image inspect alpine:latest >/dev/null 2>&1; then
    info "Pulling alpine:latest..."
    docker pull alpine:latest
fi

# Activate virtualenv if present
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

# Run doctor
step "1. Doctor Check"
patchguard doctor

# Initialize demo repo
DEMO_REPO=$(mktemp -d /tmp/patchguard-demo-XXXX)
info "Creating demo repo at $DEMO_REPO"
cd "$DEMO_REPO"
git init -b main
git config user.email "demo@patchguard.test"
git config user.name "Demo"
cat > hello.py << 'PYEOF'
def greet(name: str = "World") -> str:
    return f"Hello, {name}!"

if __name__ == "__main__":
    print(greet())
PYEOF
git add hello.py && git commit -m "initial"

# Run 1: Agent modifies hello.py
step "2. Run Agent (modify hello.py)"
patchguard run \
  --repo "$DEMO_REPO" \
  --image alpine:latest \
  --timeout 30 \
  -- sh -c "echo 'print(\"Hello, PatchGuard!\")' > /workspace/hello.py"

# Check source unchanged (INV-001)
step "3. Verify INV-001 (source workspace unchanged)"
ORIGINAL=$(cat hello.py)
info "Original hello.py still: $ORIGINAL"
if echo "$ORIGINAL" | grep -q "Hello, World!"; then
    info "INV-001: PASSED — source workspace NOT modified"
else
    warn "INV-001: FAILED — source was modified!"
fi

# List runs
step "4. List Runs"
RUN_ID=$(patchguard list --limit 1 2>/dev/null | tail -1 | awk '{print $1}')
info "Latest run: $RUN_ID"

# Inspect
step "5. Inspect Run"
patchguard inspect "$RUN_ID"

# Replay
step "6. Replay Patch (no agent re-invocation)"
patchguard replay "$RUN_ID" --repo "$DEMO_REPO"

# Policy Demo
step "7. Policy Engine Demo"
info "Attempting to run destructive command in sandbox..."
info "(Policy engine detects and logs the risk — Tier 0 logs but Tier 2 would block)"
patchguard run \
  --repo "$DEMO_REPO" \
  --image alpine:latest \
  --timeout 30 \
  -- sh -c "echo 'policy test: git reset --hard would be blocked at Tier 2'" || true

# Check HTML report
LAST_RUN=$(patchguard list --limit 1 2>/dev/null | tail -1 | awk '{print $1}')
REPORT="$HOME/.patchguard/runs/$LAST_RUN/report.html"
if [ -f "$REPORT" ]; then
    step "8. HTML Report Available"
    info "Report: $REPORT"
fi

# Cleanup
step "Cleanup"
rm -rf "$DEMO_REPO"
info "Demo repo removed: $DEMO_REPO"

echo ""
info "Demo complete. Run artifacts preserved in ~/.patchguard/runs/"
