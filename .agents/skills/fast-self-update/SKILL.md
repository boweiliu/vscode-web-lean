---
name: fast-self-update
description: Land a staged OpenHost app update the quick way - merge the new version, rebuild, restart. Use when OpenHost has redeployed a newer app version and the pending-update marker is set. For pulling from the GitHub upstream template, or when you want validation and an approval gate, use `update-self` instead.
---

# Landing an OpenHost app update, fast

When OpenHost redeploys a newer version of this app, its entrypoint stages the
new commit into this workspace as a local git ref and writes a pending-update
marker. Landing it needs only a handful of deterministic steps, so a script does
all of them and you step in exactly once: **if the merge conflicts**.

This is the fast path. It does **not** back up, validate, run the test suite, or
auto-roll-back, and it has no approval gate. Use `update-self` when you want
those -- it dispatches a worker, validates the merged tree, and asks the user
before applying.

## Just run it

```bash
python3 .agents/skills/fast-self-update/scripts/fast_self_update.py run
```

Exit codes:

- **0** -- updated and the UI came back healthy. Tell the user what changed
  (`git log --oneline HEAD@{1}..HEAD`) and mention anything the script reported
  as needing a rebuild. Done.
- **3** -- nothing staged, or already up to date. Say so; do nothing else.
- **2** -- merge conflicts. This is your one job; see below.
- **1** -- something else failed. The output names the failing command. The
  pre-merge SHA is printed and saved to `runtime/fast-self-update/rollback_sha`.

## Resolving conflicts (the only part that needs you)

On exit 2 the script prints each conflicted path and stops with the merge still
open. Nothing has been rebuilt or restarted, so the running workspace is
untouched.

Resolve each file on its merits -- keep the user's local intent, take upstream's
improvement, or genuinely combine them. Then:

```bash
git add <each resolved path>
python3 .agents/skills/fast-self-update/scripts/fast_self_update.py continue
```

`continue` refuses to proceed while any path is still conflicted, commits the
merge, and applies the rest.

To bail out instead, `git merge --abort` returns the workspace to exactly where
it was; the pending marker stays set, so the update is re-offered next boot.

If a conflict is a real product decision rather than a mechanical one -- the two
sides changed the same behaviour incompatibly -- ask the user before choosing,
the way `update-self` does. Don't silently pick.

## What the script actually does

Derived from the changed paths, in this order:

| Change | Step |
| --- | --- |
| root `pyproject.toml` / `uv.lock` | `uv sync --all-packages` |
| `apps/system_interface/pyproject.toml` | `uv tool install -e apps/system_interface --reinstall` |
| frontend `package.json` / lockfile | `npm ci` |
| any `frontend/src/**` | `npm run build` |
| always | `mngr start --restart system-services` |

Then it health-checks the live UI and, only on success, records the reconcile
via `openhost_template_update.py mark-reconciled` so the next boot does not
re-prompt.

The dependency refreshes are not optional: a manifest change followed by a bare
restart crashes the service, because the installed tool still carries the old
dependency set. The restart is unconditional because a template update can also
touch `supervisord.conf`, `bootstrap`, shared `libs/**`, and `scripts/**`, which
only a fresh process start picks up.

`python3 .agents/skills/fast-self-update/scripts/fast_self_update.py status`
prints the plan as JSON without changing anything.

## What it deliberately cannot do

Some changes a running container simply cannot adopt. The script detects and
reports them rather than pretending they landed -- **relay these to the user**,
because they need a workspace rebuild:

- **`scripts/setup_system.sh` / `install_secret_scanners.sh`** -- pinned
  toolchain versions (claude, latchkey, uv, ttyd, ...). The globally-installed
  CLIs stay at their old versions. Re-running the provisioner in-place is
  possible (`bash scripts/setup_system.sh`) but slow and network-bound, so the
  fast path leaves it to you and the user.
- **`Dockerfile`** -- image layers; needs a rebuild.
- **`.mngr/**`** -- governs future `mngr create`, not this already-running
  container.

## Undoing a bad update

The pre-merge SHA is printed and written to
`runtime/fast-self-update/rollback_sha`:

```bash
git reset --hard "$(cat runtime/fast-self-update/rollback_sha)"
mngr start --restart system-services
```
