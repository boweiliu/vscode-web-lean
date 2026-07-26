---
title: VS Code Web for Lean
description: A browser-based Lean 4 IDE: VS Code (code-server) in a workspace tab with an integrated terminal, the Lean 4 extension, and a working interactive InfoView -- served same-origin behind the workspace proxy.
thumbnail: inspiration-vscode-web-lean.svg
format: v1
---

# VS Code Web for Lean

This file is the manifest for the **VS Code Web for Lean** inspiration (slug:
`vscode-web-lean`). It is the one document a future agent reads to understand,
present, and adapt this inspiration. If you are an agent in a mind that was
created from this inspiration, this file is your script: read all of it, then
follow "How to adapt it" below.

## What it is

A browser-based Lean 4 IDE: VS Code (code-server) in a workspace tab with an integrated terminal, the Lean 4 extension, and a working interactive InfoView -- served same-origin behind the workspace proxy.

This inspiration gives a mind a full Lean 4 development environment that lives
entirely in the browser -- no local install of Lean, VS Code, or a toolchain.
It runs code-server (the open-source build of VS Code for the web) as a
supervised background service and exposes it as a single workspace tab at
`/service/lean-ide/`. When the user opens that tab they see a real VS Code
window: a file tree, a syntax-highlighted editor with the official Lean 4
extension (live diagnostics, go-to-definition, autocomplete), an integrated
terminal whose PATH already has the Lean toolchain (`elan`/`lean`/`lake`) so
they can `lake build` and run programs, and -- the piece that is usually the
hardest to get working through a proxy -- a live interactive InfoView panel that
shows proof goals and expected types as the cursor moves through a proof. The
tab opens on a bundled `lean_playground` Lake project preloaded with runnable
starter programs (a hello world, and a stdin-driven arbitrary-precision
Fibonacci calculator) plus several small educational Lean files (a `Prop`
vs `Type` "evidence erasure" demo, and tactic/compiler diagnostic-view demos)
so there is something to edit, build, and step through from the first boot. The
problem it solves: standing up a genuinely usable, single-origin web IDE for a
compiled language behind the workspace proxy -- most of the engineering here is
the set of fixes that make code-server (and its webviews) render correctly when
served under a path-rewriting service-worker proxy rather than at its own
origin.

## How it works

The snapshot includes these paths (each is a repo-root-relative path copied
from the original mind onto a clean default-workspace-template base):

- `lean-workspace`
- `scripts/run_lean_ide.sh`
- `scripts/patch_code_server.py`
- `apps/system_interface/imbue/system_interface/proxy.py`
- `apps/system_interface/imbue/system_interface/proxy_test.py`
- `apps/system_interface/imbue/system_interface/service_dispatcher.py`
- `apps/system_interface/imbue/system_interface/service_dispatcher_test.py`

What each included path is and does:

- `lean-workspace/` -- the `lean_playground` Lake project (data, not code the
  service runs): a `lakefile.toml`, a pinned `lean-toolchain`, two runnable
  programs (`HelloWorld.lean` -> `hello`; `Fibonacci.lean` -> `fib`, a stdin
  arbitrary-precision Fibonacci calculator) and three educational Lean files
  (`InfoviewDemo.lean`, `EvidenceErasure.lean`, `TacticDebugViews.lean`). This
  is the folder the editor opens by default, so the IDE has real content on
  first boot.
- `scripts/run_lean_ide.sh` -- the self-bootstrapping launcher run by the
  `lean-ide` supervisord service. On first run it idempotently installs the Lean
  toolchain via `elan`, installs code-server, installs the `leanprover.lean4`
  extension, and seeds code-server user settings (terminal PATH + Lean toolchain
  path). On every run it re-applies the proxy-compat patches, registers the
  service port, and `exec`s code-server.
- `scripts/patch_code_server.py` -- seven idempotent source patches to
  code-server (which lives outside the repo under `/usr/lib/code-server`, so a
  rebuild reverts them; the launcher re-runs this each boot). These are what
  make code-server render behind the proxy (details below).
- `apps/system_interface/imbue/system_interface/{proxy,service_dispatcher}.py`
  (+ their `_test.py` files) -- the ONE change to the workspace UI: the proxy
  now leaves VS Code webview iframe documents untouched instead of injecting its
  usual `<base>` tag + WebSocket shim into them. This is what makes the
  interactive InfoView actually render.

How it wires together at runtime. The `[program:lean-ide]` supervisord program
runs `scripts/run_lean_ide.sh` (wrapped by `oom_tag_service.py user`, so it is
shed before built-in services under memory pressure). The launcher binds
code-server to loopback `127.0.0.1:8090` with `--auth none` (the workspace's own
authentication sits in front of it) and registers it with the system_interface
proxy by calling `scripts/forward_port.py --url http://localhost:8090 --name
lean-ide`, which mounts it at `/service/lean-ide/`. The system_interface service
(already in the base template) is the front door: it terminates the user's
request, and its path-rewriting *service worker* rewrites resource URLs so a
single-origin app works under a `/service/<name>/` prefix. That service worker
is the root cause of most of the patches:

- code-server's own PWA service worker would evict the proxy's worker at the
  service-root scope -- patch #1 removes it.
- code-server 302-redirects `/` -> `./?folder=...`; the proxy forwards
  navigations with `redirect:'manual'`, so that 302 aborts the navigation and
  the workbench never mounts -- patch #2 injects the folder into the query and
  serves the workbench directly instead. Patch #6 then bakes the
  `lean_playground` folder into the served config so a query-less refresh still
  opens the project.
- code-server's strict workbench CSP (nonce-based) blocks the proxy's injected
  scripts -- patch #3 drops that header (safe: loopback, behind workspace auth).
- code-server serves brotli, but the proxy's httpx client has no brotli/zstd
  decoder and strips `Content-Encoding` without decoding -- patch #4 disables
  compression so bodies pass through as identity.
- code-server's `Connection: keep-alive` collides with Flask's own
  `Connection: close`, stalling render-blocking subresources -- patch #5 forces
  `Connection: close` on every response.
- The InfoView is the subtle one: code-server serves webview iframe documents
  same-origin (no subdomain needed) from a deep `.../webview/browser/pre/` path,
  but each webview registers its service worker at the SERVICE ROOT with root
  scope so it can intercept every `vscode-resource` request. code-server ships
  that worker only under the deep path, so the root request 404s and
  registration fails ("bad HTTP response code (404)") -- the InfoView never
  loads. Patch #7 adds an Express route that serves JUST `service-worker.js` at
  the root (with `Service-Worker-Allowed: /`), deliberately leaving the iframe
  document on its native deep path. Paired with the proxy change (the proxy no
  longer rewrites those deep webview documents, which would otherwise corrupt
  their CSP and relative-path resolution), this is what makes the interactive
  InfoView render end-to-end.

## Prerequisites

Activation requirements: what the adopting agent must SET UP -- and must
INITIATE ITSELF during setup, before asking how to adapt -- for this
inspiration to run against the new user's own accounts/data. One line per
requirement, in this machine-readable form (greppable by `requires_`):

No latchkey permissions or secrets required. This is a self-contained local
development tool -- it does not call any third-party account on the user's
behalf, so there is nothing to authorize and no token to configure.

The one real requirement is outbound internet access on first boot: the
launcher downloads the Lean toolchain (`elan`/Lean from leanprover), code-server
(from code-server.dev), and the Lean 4 extension (from open-vsx.org). Because
these are fetched and installed the first time the service starts, the first
boot is slow and the IDE tab is not usable until those downloads finish;
subsequent boots reuse the installed toolchain and are fast. No prerequisites
beyond that network access.

## How to adapt it

Instructions for the NEXT agent -- the one adapting this inspiration into a
new mind. This is the `use-inspiration` skill's template path; in short:

1. Read this entire file first, especially "Prerequisites" and "Holes"
   below -- Prerequisites are your SETUP agenda, Holes are your ADAPTATION
   agenda.
2. Present the inspiration to the user in plain, non-technical language: what
   it is, what it does, and what it needs from them (name the Prerequisites).
3. Ask whether they want to use the same connectors (e.g. their own Slack).
   If YES: ACTIVATE FIRST -- initiate every `requires_permission` line NOW
   via a latchkey permission request (see the `latchkey` skill; the request
   opens the approval/login flow in the minds app), wire up any
   `requires_secret` values, start the services, and get the app showing
   THE USER'S OWN DATA. Done for a data-backed app means the user can open it
   and see their own data -- NOT that a service starts or an endpoint returns
   200. Then tell them it is live and to take a look.
4. Only AFTER that (or immediately, if they chose different connectors -- the
   swap is then the first adaptation) ask: "How do you want to adapt it?"
5. Work through each hole interactively, one at a time. Translate each into
   plain language, ask for a decision only when you genuinely need one, and
   resolve the obvious ones yourself.
6. When done, append a dated entry to "Adaptation history" below (never
   rewrite earlier entries) and commit.

## Holes

These are adaptation notes, not activation requirements -- the app boots and
works as-is. They are the things an adopter should be aware of when they extend
or update it:

- **The bundled `apps/system_interface` carries a one-line webview fix.** This
  snapshot overlays a modified system_interface: its proxy leaves VS Code
  webview iframe documents (paths under `.../webview/browser/pre/`) untouched
  instead of rewriting them, which is what makes the InfoView render. An adopter
  who later refreshes their system_interface from upstream must preserve that
  guard (the `is_webview_document_path` check in `proxy.py` and its use in
  `service_dispatcher.py`) -- or upstream it -- or the interactive InfoView will
  break again. A working replacement is simply re-applying that guard on top of
  the newer system_interface.
- **First boot downloads a large toolchain over the network and is slow.**
  code-server, the Lean toolchain, and the Lean 4 extension are all fetched on
  the first start (see Prerequisites). Nothing to rewire, but expect the tab to
  show "Loading..." / be unavailable until the initial install completes.
- **The proxy patches target a specific code-server version's internals.**
  `patch_code_server.py` matches exact source strings inside code-server's
  compiled JS (`server-main.js`, `routes/vscode.js`, `app.js`,
  `routes/index.js`). It is idempotent and fails loudly *per patch* if an anchor
  string is missing (it prints which patch did not apply and skips it rather
  than corrupting the file). A substantially different code-server version could
  move those anchors; the fix is to update the corresponding `*_OLD` string in
  `patch_code_server.py` to match the new code-server layout. The
  well-documented module docstring explains what each of the seven patches does,
  which makes re-anchoring straightforward.

## Adaptation history

Each mind that adapts this inspiration appends one dated entry below. Earlier
entries are never rewritten.
