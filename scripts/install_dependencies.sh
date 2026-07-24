#!/usr/bin/env bash
# Shared dependency install for default-workspace-template hosts.
#
# Installs third-party Python + Node dependencies from the lockfiles only (no
# workspace/local packages). Needs the dependency manifests present but not the
# full source, so the Dockerfile runs it right after copying the manifests (to
# preserve layer caching) and the Lima provider runs it after the repo is synced
# into the VM. Runs as root and is idempotent.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
export PATH="/root/.local/bin:$PATH"

# NOTE: intentionally NOT guarded by the provisioning skip cache -- this produces
# in-repo outputs (.venv, node_modules) that the create's git-mirror landing does
# not carry, so it must run on every create to regenerate them (fast via the
# baked warm uv/npm caches). Only setup_system (global-only effects) is skipped.

# Pin uv to a Python that satisfies the lockfile (>=3.12). The Docker base ships
# 3.12; on other bases setup_system.sh fetched a uv-managed 3.12, so point uv at
# it. No-op when system Python is already >=3.12 (Docker build unchanged).
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
    export UV_PYTHON=3.12
fi

REPO_ROOT="${REPO_ROOT:-/mngr/code}"

# The Python and JavaScript installs touch disjoint trees (.venv vs
# node_modules) and neither reads the other's output, so they run concurrently.
# Their progress output interleaves in the build log.

# Pre-warm the uv wheel cache: install every third-party PyPI dep in the
# lockfile, skipping workspace + local path packages (build_workspace.sh
# registers those once the full source is present).
(cd "$REPO_ROOT" && uv sync --all-packages --frozen --no-install-workspace --no-install-local) &
uv_pid=$!

# Frontend npm dependencies (exact, from the lockfile).
(cd "$REPO_ROOT/apps/system_interface/frontend" && npm ci) &
npm_pid=$!

# Wait for both before reporting, so a failure names every install that failed
# rather than only the first.
uv_status=0
npm_status=0
wait "$uv_pid" || uv_status=$?
wait "$npm_pid" || npm_status=$?
if [ "$uv_status" -ne 0 ] || [ "$npm_status" -ne 0 ]; then
    echo "install_dependencies: uv sync exited ${uv_status}, npm ci exited ${npm_status}" >&2
    exit 1
fi
