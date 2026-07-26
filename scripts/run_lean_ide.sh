#!/usr/bin/env bash
# Launch code-server (VS Code in the browser) for Lean development.
#
# On first run this bootstraps everything it needs (idempotently): the Lean
# toolchain (elan/lean/lake), code-server, and the Lean 4 VS Code extension.
# Then it re-applies the proxy-compat patches, registers the service port with
# the system_interface proxy, and execs code-server bound to loopback, opened on
# the lean_playground Lake project.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

export PATH="$HOME/.elan/bin:$HOME/.local/bin:$PATH"

PORT=8090
NAME=lean-ide
PROJECT_DIR="$REPO_ROOT/lean-workspace/lean_playground"
# patch_code_server.py bakes this as the default folder in the workbench config.
export LEAN_IDE_PROJECT_DIR="$PROJECT_DIR"

# --- 1. Install the Lean toolchain (elan) if missing -------------------------
if ! command -v lean >/dev/null 2>&1; then
  echo "[run_lean_ide] installing Lean toolchain via elan..."
  curl -fsSL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh \
    | sh -s -- -y --default-toolchain stable
  # make elan available to future interactive terminals too
  grep -q 'elan/env' "$HOME/.bashrc" 2>/dev/null \
    || echo '. "$HOME/.elan/env"' >> "$HOME/.bashrc"
fi

# --- 2. Install code-server if missing ---------------------------------------
if ! command -v code-server >/dev/null 2>&1; then
  echo "[run_lean_ide] installing code-server..."
  curl -fsSL https://code-server.dev/install.sh | sh
fi

# --- 3. Install the Lean 4 extension if missing ------------------------------
if ! code-server --list-extensions 2>/dev/null | grep -qi '^leanprover.lean4$'; then
  echo "[run_lean_ide] installing the Lean 4 VS Code extension..."
  code-server --install-extension leanprover.lean4 || true
fi

# --- 4. Seed user settings (terminal PATH + Lean toolchain) once -------------
CS_USER_DIR="$HOME/.local/share/code-server/User"
if [ ! -f "$CS_USER_DIR/settings.json" ]; then
  mkdir -p "$CS_USER_DIR"
  cat > "$CS_USER_DIR/settings.json" <<JSON
{
  "terminal.integrated.env.linux": {
    "PATH": "$HOME/.elan/bin:$HOME/.local/bin:\${env:PATH}"
  },
  "terminal.integrated.defaultProfile.linux": "bash",
  "workbench.startupEditor": "none",
  "telemetry.telemetryLevel": "off",
  "security.workspace.trust.enabled": false,
  "lean4.toolchainPath": "$HOME/.elan"
}
JSON
fi

# --- 5. Apply the proxy-compat patches (idempotent; re-applied every boot
#        because code-server lives outside the repo) --------------------------
python3 scripts/patch_code_server.py

python3 scripts/forward_port.py --url "http://localhost:${PORT}" --name "${NAME}"

# The project folder is baked into the served workbench config by
# patch_code_server.py (the DEFAULT_FOLDER edit), so every load -- including a
# query-less refresh -- opens lean_playground regardless of code-server's stored
# "last opened" state. An explicit ?folder= in the URL still wins.
exec code-server \
  --bind-addr "127.0.0.1:${PORT}" \
  --auth none \
  --disable-telemetry \
  --disable-update-check \
  "${PROJECT_DIR}"
