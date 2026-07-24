"""Apply a staged OpenHost app update with no LLM in the loop except for conflicts.

The OpenHost entrypoint stages each new app version into this workspace as a
local git ref and writes a pending marker; see
``scripts/openhost_template_update.py``. Landing that update needs only a
handful of deterministic steps, so this script does all of them in one shot and
stops for a human exactly once: when the merge conflicts.

The apply plan is derived from the changed paths, mirroring what
``update-system-interface``'s reveal does, plus a workspace-level dependency
sync:

* root ``pyproject.toml`` / ``uv.lock``      -> ``uv sync --all-packages``
* ``apps/system_interface/pyproject.toml``   -> ``uv tool install -e ... --reinstall``
* frontend ``package.json`` / lockfile       -> ``npm ci``
* any frontend source                        -> ``npm run build``
* always                                     -> ``mngr start --restart system-services``

The dependency refreshes are not optional decoration: a manifest change picked
up by a bare restart crashes the service, because the installed tool still has
the old dependency set.

Some classes of change cannot be applied to a running container at all (image
layers, provisioner tool pins, mngr create-time config). Those are detected and
reported at the end rather than silently ignored -- they need a rebuild.

This is the fast path. It does not validate, snapshot, or auto-roll-back; the
`update-self` skill remains the thorough option. The pre-merge SHA is printed
and recorded so a bad update can be undone by hand.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

DEFAULT_WORKSPACE = Path("/mngr/code")
DEFAULT_INCOMING_REF = "refs/openhost/incoming"
DEFAULT_PENDING_PATH = Path("/mngr/openhost_update_pending")

APP_DIR = "apps/system_interface"
FRONTEND_DIR = f"{APP_DIR}/frontend"

WORKSPACE_URL = os.environ.get("MINDS_WORKSPACE_URL", "http://127.0.0.1:8000")
HEALTH_PATH = "/api/agents"
_HEALTH_ATTEMPTS = 30
_HEALTH_INTERVAL_SECONDS = 1.0

# State file recording the pre-merge SHA, so a bad fast update can be undone
# after the fact even though this script never rolls back on its own.
ROLLBACK_STATE = Path("runtime/fast-self-update/rollback_sha")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CONFLICTS = 2
EXIT_NOTHING_TO_DO = 3


@dataclass
class ApplyPlan:
    """Which apply steps the changed paths call for."""

    root_manifest: bool = False
    backend_manifest: bool = False
    backend_src: bool = False
    frontend_manifest: bool = False
    frontend_src: bool = False
    # Classes a running container cannot adopt; reported, never run.
    provisioner: list[str] = field(default_factory=list)
    image: list[str] = field(default_factory=list)
    create_config: list[str] = field(default_factory=list)

    @property
    def needs_frontend_build(self) -> bool:
        return self.frontend_src or self.frontend_manifest

    @property
    def rebuild_only(self) -> list[str]:
        return [*self.provisioner, *self.image, *self.create_config]


def classify(paths: list[str]) -> ApplyPlan:
    """Derive the apply plan from repo-relative changed paths."""
    plan = ApplyPlan()
    for path in paths:
        if path in ("pyproject.toml", "uv.lock"):
            plan.root_manifest = True
        if path == f"{APP_DIR}/pyproject.toml" or path == "uv.lock":
            plan.backend_manifest = True
        if path in (f"{FRONTEND_DIR}/package.json", f"{FRONTEND_DIR}/package-lock.json"):
            plan.frontend_manifest = True
        elif path.startswith(f"{FRONTEND_DIR}/src/"):
            plan.frontend_src = True
        elif path.startswith(f"{APP_DIR}/imbue/") and path.endswith(".py"):
            plan.backend_src = True

        if path in (
            "scripts/setup_system.sh",
            "scripts/install_secret_scanners.sh",
            "scripts/_provision_guard.sh",
        ):
            plan.provisioner.append(path)
        elif path == "Dockerfile":
            plan.image.append(path)
        elif path.startswith(".mngr/"):
            plan.create_config.append(path)
    return plan


def run(
    cmd: list[str],
    *,
    cwd: Path,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a command, echoing it so the transcript shows exactly what happened."""
    print(f"+ {' '.join(cmd)}  (in {cwd})", flush=True)
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=capture,
    )
    if check and result.returncode != 0:
        if capture:
            sys.stderr.write(result.stdout or "")
            sys.stderr.write(result.stderr or "")
        raise SystemExit(EXIT_ERROR)
    return result


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        text=True,
        capture_output=True,
        check=check,
    )


def _fail(message: str) -> None:
    sys.stderr.write(f"fast-self-update: {message}\n")
    raise SystemExit(EXIT_ERROR)


def resolve_target(repo: Path, ref: str) -> str:
    result = git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}", check=False)
    if result.returncode != 0:
        _fail(f"incoming ref {ref!r} does not exist; nothing staged to update from")
    return result.stdout.strip()


def changed_paths(repo: Path, base: str, target: str) -> list[str]:
    result = git(repo, "diff", "--name-only", base, target)
    return [line for line in result.stdout.splitlines() if line.strip()]


def conflicted_paths(repo: Path) -> list[str]:
    result = git(repo, "diff", "--name-only", "--diff-filter=U")
    return [line for line in result.stdout.splitlines() if line.strip()]


def require_clean_tree(repo: Path) -> None:
    result = git(repo, "status", "--porcelain")
    if result.stdout.strip():
        _fail(
            "working tree is not clean; commit or stash first:\n" + result.stdout.rstrip()
        )


def record_rollback_sha(repo: Path, sha: str) -> None:
    path = repo / ROLLBACK_STATE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{sha}\n")


def wait_healthy() -> bool:
    """Poll the live system interface until it answers, or give up."""
    url = f"{WORKSPACE_URL}{HEALTH_PATH}"
    for _ in range(_HEALTH_ATTEMPTS):
        try:
            with urllib.request.urlopen(url, timeout=5.0) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(_HEALTH_INTERVAL_SECONDS)
    return False


def apply_plan(repo: Path, plan: ApplyPlan) -> None:
    """Run the deterministic apply steps, in dependency order."""
    if plan.root_manifest:
        run(["uv", "sync", "--all-packages"], cwd=repo)
    if plan.backend_manifest:
        run(["uv", "tool", "install", "-e", APP_DIR, "--reinstall"], cwd=repo)
    if plan.frontend_manifest:
        run(["npm", "ci"], cwd=repo / FRONTEND_DIR)
    if plan.needs_frontend_build:
        run(["npm", "run", "build"], cwd=repo / FRONTEND_DIR)
    # Always restart: beyond the system interface itself, a template update can
    # touch supervisord.conf, bootstrap, shared libs, and scripts that only the
    # next process start picks up.
    run(["mngr", "start", "--restart", "system-services"], cwd=repo)


def mark_reconciled(repo: Path, target: str, pending: Path) -> None:
    run(
        [
            "python3",
            "scripts/openhost_template_update.py",
            "mark-reconciled",
            "--version",
            target,
            "--pending",
            str(pending),
        ],
        cwd=repo,
    )


def report(plan: ApplyPlan, target: str, rollback_sha: str, healthy: bool) -> None:
    print()
    print(f"fast-self-update: applied {target}")
    print(f"  previous HEAD (rollback point): {rollback_sha}")
    print(f"  live system interface healthy: {'yes' if healthy else 'NO'}")
    if plan.rebuild_only:
        print()
        print("  NOT applied -- these need a workspace rebuild, not a restart:")
        for path in plan.provisioner:
            print(f"    {path} (pinned toolchain; re-run scripts/setup_system.sh or rebuild)")
        for path in plan.image:
            print(f"    {path} (image layer)")
        for path in plan.create_config:
            print(f"    {path} (governs future `mngr create`, not this container)")
    if not healthy:
        print()
        print("  The UI did not come back healthy. To undo:")
        print(f"    git reset --hard {rollback_sha} && mngr start --restart system-services")


def finish(repo: Path, target: str, plan: ApplyPlan, rollback_sha: str, pending: Path) -> int:
    apply_plan(repo, plan)
    healthy = wait_healthy()
    if healthy:
        mark_reconciled(repo, target, pending)
    report(plan, target, rollback_sha, healthy)
    return EXIT_OK if healthy else EXIT_ERROR


def cmd_run(args: argparse.Namespace) -> int:
    repo = Path(args.workspace)
    pending = Path(args.pending)
    target = resolve_target(repo, args.ref)
    head = git(repo, "rev-parse", "HEAD").stdout.strip()

    if git(repo, "merge-base", "--is-ancestor", target, head, check=False).returncode == 0:
        print(f"fast-self-update: {target} is already in HEAD; nothing to do")
        return EXIT_NOTHING_TO_DO

    require_clean_tree(repo)
    base = git(repo, "merge-base", "HEAD", target).stdout.strip()
    plan = classify(changed_paths(repo, base, target))
    record_rollback_sha(repo, head)

    merge = subprocess.run(
        ["git", "merge", "--no-edit", args.ref],
        cwd=str(repo),
        text=True,
        capture_output=True,
    )
    print(merge.stdout, end="")
    if merge.returncode != 0:
        conflicts = conflicted_paths(repo)
        if not conflicts:
            sys.stderr.write(merge.stderr)
            _fail("merge failed for a reason other than conflicts")
        sys.stderr.write(
            "fast-self-update: merge conflicts need a human decision:\n"
            + "".join(f"  {path}\n" for path in conflicts)
            + "\nResolve them, `git add` each, then re-run with `continue`.\n"
            f"To bail out instead: git merge --abort (returns to {head}).\n"
        )
        return EXIT_CONFLICTS

    return finish(repo, target, plan, head, pending)


def cmd_continue(args: argparse.Namespace) -> int:
    """Complete a conflicted merge the caller has resolved, then apply."""
    repo = Path(args.workspace)
    pending = Path(args.pending)
    target = resolve_target(repo, args.ref)

    remaining = conflicted_paths(repo)
    if remaining:
        _fail(
            "these paths are still conflicted:\n"
            + "".join(f"  {path}\n" for path in remaining)
        )

    rollback_path = repo / ROLLBACK_STATE
    rollback_sha = rollback_path.read_text().strip() if rollback_path.exists() else "unknown"

    if (repo / ".git" / "MERGE_HEAD").exists():
        run(["git", "commit", "--no-edit"], cwd=repo)

    base = git(repo, "merge-base", rollback_sha, target).stdout.strip() if rollback_sha != "unknown" else ""
    paths = changed_paths(repo, base, target) if base else changed_paths(repo, f"{target}~1", target)
    return finish(repo, target, classify(paths), rollback_sha, pending)


def cmd_status(args: argparse.Namespace) -> int:
    """Show what is staged and what the apply plan would be. Changes nothing."""
    repo = Path(args.workspace)
    target = resolve_target(repo, args.ref)
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    if git(repo, "merge-base", "--is-ancestor", target, head, check=False).returncode == 0:
        print(json.dumps({"pending": False, "target": target}, indent=2))
        return EXIT_NOTHING_TO_DO
    base = git(repo, "merge-base", "HEAD", target).stdout.strip()
    paths = changed_paths(repo, base, target)
    plan = classify(paths)
    print(
        json.dumps(
            {
                "pending": True,
                "target": target,
                "head": head,
                "changed_file_count": len(paths),
                "steps": {
                    "uv sync --all-packages": plan.root_manifest,
                    "uv tool install --reinstall": plan.backend_manifest,
                    "npm ci": plan.frontend_manifest,
                    "npm run build": plan.needs_frontend_build,
                    "mngr start --restart system-services": True,
                },
                "rebuild_only": plan.rebuild_only,
            },
            indent=2,
        )
    )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, handler, help_text in (
        ("run", cmd_run, "Merge the staged update and apply it"),
        ("continue", cmd_continue, "Finish after resolving merge conflicts"),
        ("status", cmd_status, "Show the pending update and apply plan"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--workspace", default=str(DEFAULT_WORKSPACE))
        p.add_argument(
            "--ref",
            default=os.environ.get("OPENHOST_TEMPLATE_INCOMING_REF", DEFAULT_INCOMING_REF),
        )
        p.add_argument(
            "--pending",
            default=os.environ.get("OPENHOST_UPDATE_PENDING_PATH", str(DEFAULT_PENDING_PATH)),
        )
        p.set_defaults(handler=handler)
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
