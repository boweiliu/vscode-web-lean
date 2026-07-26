#!/usr/bin/env python3
"""Idempotently patch code-server so it renders behind the system_interface proxy.

code-server lives outside the repo (installed under /usr/lib/code-server via the
distro package), so a reinstall or image rebuild would revert these edits. The
lean-ide wrapper (scripts/run_lean_ide.sh) runs this on every boot to re-apply
them if needed.

Two edits, both driven by the same root cause -- the workspace UI proxies a
service at /service/<name>/ using an injected, path-rewriting *service worker*,
and code-server's defaults collide with it:

1. Drop code-server's own PWA service worker registration. It registers at the
   service-root scope and would replace the proxy's service worker, so dynamic
   workbench fetches lose their /service/<name>/ prefix and the editor stalls at
   "Loading...". Removing the `serviceWorker:{...}` product config makes
   code-server never register one, leaving the proxy's worker in sole control.

2. Stop the 302 redirect on "/". When a folder/workspace is opened, code-server
   redirects "/" -> "./?folder=..."; the proxy's service worker forwards
   navigations with redirect:'manual', so that 302 aborts the navigation
   (net::ERR_ABORTED) and the workbench never mounts. We inject the folder into
   the request query and fall through to serve the workbench directly instead.

3. Drop the Content-Security-Policy on the workbench HTML response. code-server
   sends a strict script-src with a nonce, which blocks the inline scripts the
   proxy injects into the page (the <base> tag + WebSocket shim, and the
   service-worker bootstrap). Because a nonce is present, 'unsafe-inline' would
   be ignored, so the whole header is removed. Safe here: the service is bound to
   loopback and sits behind the workspace's own authentication.

4. Disable code-server's HTTP response compression. Its express `compression()`
   middleware serves brotli when the browser offers it, but the system_interface
   proxy forwards responses through an httpx client with no brotli/zstd decoder.
   The proxy strips the Content-Encoding header without decoding, so the browser
   receives undecodable bytes labelled as plain HTML and the workbench renders as
   garbage. Disabling compression makes code-server serve identity only (which
   httpx passes through untouched). Over loopback the extra bytes are irrelevant.

5. Force `Connection: close` on every response. code-server sends
   `Connection: keep-alive` + `Keep-Alive: timeout=5`. These are hop-by-hop
   headers; the system_interface proxy forwards them unchanged, and Flask then
   also appends its own `Connection: close`, so the browser receives two
   contradictory Connection headers. It honours keep-alive and tries to reuse the
   TCP socket for the render-blocking workbench.css/js, but the upstream Werkzeug
   connection was already closed, so those parser-blocking subresources stall and
   the workbench never boots (readyState stuck at "loading"). Making code-server
   emit only `Connection: close` removes the contradiction. Over loopback,
   per-request connections are fine. Installed as an Express middleware in the
   same edit that disables compression.

6. Bake the lean_playground folder into the served workbench config. VS Code's
   web workbench reads the open folder from the browser URL; the original
   mechanism to set it was a 302 redirect appending `?folder=`, which patch #2
   removed for proxy compatibility. As a result a query-less load (any refresh)
   opened an empty window and lost the folder selection. The web config builder
   sets `folderUri` from a `default-folder` arg that code-server does not expose
   on its CLI, so we give that arg lookup a fallback to the project path. Now
   every load -- including a refresh -- opens lean_playground, while an explicit
   `?folder=` in the URL still takes precedence.

7. Serve ONLY the webview service worker at the service root. VS Code webviews
   (the Lean InfoView, markdown preview, the Welcome page) load their iframe
   document from the deep `.../webview/browser/pre/` path, but register their
   service worker at the SERVICE ROOT with root scope
   (`register('/service/lean-ide/service-worker.js')`, scope `/service/lean-ide/`)
   so the worker can intercept every `vscode-resource` request in the webview.
   code-server ships that worker only under the deep path, so the root request
   404s -- registration fails with "bad HTTP response code (404)" and the webview
   never loads its resources (the Lean infoview's index.css/webview.js). We add an
   Express route that serves JUST `service-worker.js` at root, with
   `Service-Worker-Allowed: /`. We deliberately do NOT serve `fake.html` /
   `index.html` at root: doing so pulls the webview host iframe itself to the root
   path, which breaks the worker's parent-client lookup (`getOuterIframeClient`
   matches the host iframe on the deep `pre/` path) and also risks shadowing the
   workbench's own `/` route. So the iframe stays deep, only the worker is at
   root -- exactly what the webview expects.

Each edit is applied only if its exact target string is present, and verifies the
replacement afterwards, so running this repeatedly is safe.
"""
import os
import sys
from pathlib import Path

SERVER_MAIN = Path("/usr/lib/code-server/lib/vscode/out/server-main.js")
VSCODE_ROUTE = Path("/usr/lib/code-server/out/node/routes/vscode.js")
APP_JS = Path("/usr/lib/code-server/out/node/app.js")
INDEX_ROUTE = Path("/usr/lib/code-server/out/node/routes/index.js")

# Replace the serviceWorker product config with a harmless, detectable marker
# (an empty replacement would make the "already patched" check below always true,
# since "" is a substring of everything).
SW_CONFIG_OLD = 'serviceWorker:{scope:s+"/",path:i+"/_static/out/browser/serviceWorker.js"},'
SW_CONFIG_NEW = "/*minds-no-sw*/"

REDIRECT_OLD = """        if (folder || workspace) {
            return (0, http_1.redirect)(req, res, to, {
                folder,
                workspace,
            });
        }
    }"""

REDIRECT_NEW = """        if (folder || workspace) {
            // Minds patch: serving the workbench directly with the folder/workspace
            // injected into req.query instead of issuing a 302 redirect. The
            // system_interface proxy's path-rewriting service worker forwards
            // navigations with redirect:'manual', so a 302 on "/" aborts the
            // navigation (net::ERR_ABORTED) and the workbench never mounts behind
            // /service/lean-ide/. Falling through avoids the redirect entirely.
            if (folder)
                req.query.folder = folder;
            if (workspace)
                req.query.workspace = workspace;
        }
    }"""

# Drop the CSP header on the workbench HTML response (see module docstring #3).
CSP_OLD = "e.writeHead(200,K)"
CSP_NEW = 'delete K["Content-Security-Policy"],e.writeHead(200,K)'

# Disable response compression so httpx (no br/zstd decoder) can pass bodies
# through untouched (see module docstring #4). Neutralize the middleware call and,
# in the same edit, install a middleware that forces Connection: close on every
# response (see module docstring #5).
COMPRESSION_OLD = "router.use((0, compression_1.default)());"
COMPRESSION_NEW = (
    "/* Minds patch: compression disabled for proxy compatibility */ void compression_1;"
    " router.use((req, res, next) => { res.setHeader('Connection', 'close');"
    " res.removeHeader('Keep-Alive'); next(); });"
)

# Bake the project folder into the served workbench config (see module docstring
# #6). The web config sets folderUri from the `default-folder` arg, which
# code-server does not expose on its CLI; we replace the arg lookup with a
# fallback to the lean_playground path so every load opens there. `P` is
# code-server's path->URI helper (returns undefined for undefined input), so an
# explicit ?folder= still overrides this via the normal query path.
DEFAULT_FOLDER = os.environ.get(
    "LEAN_IDE_PROJECT_DIR", "/mngr/code/lean-workspace/lean_playground"
)
FOLDER_OLD = 'folderUri:P(this._environmentService.args["default-folder"])'
FOLDER_NEW = f'folderUri:P(this._environmentService.args["default-folder"]||"{DEFAULT_FOLDER}")'

# Serve ONLY the webview service worker at the service root (see module docstring
# #7). VS Code webviews load their iframe document from the deep .../pre/ path
# (correct -- leave that alone), but they register the service worker at the
# SERVICE ROOT with root scope: register('/service/lean-ide/service-worker.js')
# scope '/service/lean-ide/'. code-server ships that worker only under the deep
# path, so the root request 404s and registration fails. Add an Express route
# that serves JUST service-worker.js at root, with Service-Worker-Allowed:/.
# Crucially we do NOT serve fake.html/index.html at root -- doing so pulls the
# webview iframe itself to the root path and breaks the SW's parent-client
# lookup (getOuterIframeClient expects the host iframe on the deep path). `path`,
# `express`, and `constants_1` are already imported in this module.
SW_ROUTE_OLD = "    app.router.use(express.urlencoded({ extended: true }));"
SW_ROUTE_NEW = (
    "    app.router.use(express.urlencoded({ extended: true }));\n"
    "    /* Minds patch: serve ONLY the webview service worker at the service root\n"
    "       (root-scoped registration) so webviews (Lean InfoView etc.) work behind\n"
    "       the proxy. Deliberately NOT fake.html/index.html -- the iframe document\n"
    "       must stay on its native deep .../pre/ path. */\n"
    "    app.router.get('/service-worker.js', (req, res) => {\n"
    "        res.setHeader('Service-Worker-Allowed', '/');\n"
    "        res.setHeader('Content-Type', 'text/javascript');\n"
    "        res.sendFile(path.join(constants_1.vsRootPath,\n"
    "            'out/vs/workbench/contrib/webview/browser/pre/service-worker.js'));\n"
    "    });"
)


def patch_file(path: Path, old: str, new: str, label: str) -> bool:
    """Apply one replacement. Returns True if a change was written."""
    if not path.exists():
        print(f"[patch_code_server] MISSING {path} -- skipping {label}", file=sys.stderr)
        return False
    text = path.read_text()
    if new in text:
        print(f"[patch_code_server] {label}: already patched")
        return False
    count = text.count(old)
    if count != 1:
        print(
            f"[patch_code_server] {label}: expected exactly 1 match, found {count} "
            f"-- code-server layout may have changed; skipping",
            file=sys.stderr,
        )
        return False
    path.write_text(text.replace(old, new))
    print(f"[patch_code_server] {label}: patched")
    return True


def main() -> int:
    patch_file(SERVER_MAIN, SW_CONFIG_OLD, SW_CONFIG_NEW, "drop PWA service worker registration")
    patch_file(VSCODE_ROUTE, REDIRECT_OLD, REDIRECT_NEW, "serve workbench without 302 redirect")
    patch_file(SERVER_MAIN, CSP_OLD, CSP_NEW, "drop workbench CSP header")
    patch_file(APP_JS, COMPRESSION_OLD, COMPRESSION_NEW, "disable response compression")
    patch_file(SERVER_MAIN, FOLDER_OLD, FOLDER_NEW, "bake in default project folder")
    patch_file(INDEX_ROUTE, SW_ROUTE_OLD, SW_ROUTE_NEW, "serve webview service worker at root")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
