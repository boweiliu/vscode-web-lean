# VS Code Web for Lean

A browser-based Lean 4 IDE: VS Code (code-server) in a workspace tab with an integrated terminal, the Lean 4 extension, and a working interactive InfoView -- served same-origin behind the workspace proxy.

This inspiration turns a mind into a full Lean 4 development environment that
runs entirely in the browser -- no local install of Lean, VS Code, or a
toolchain. It runs code-server (open-source VS Code for the web) as a supervised
service and exposes it as a single workspace tab: a real VS Code window with a
file tree, the official Lean 4 extension (live diagnostics, go-to-definition),
an integrated terminal with the Lean toolchain (`elan`/`lean`/`lake`) already on
PATH, and a working interactive InfoView showing proof goals and types. It opens
on a bundled `lean_playground` Lake project with runnable starter programs, so
there is something to build and step through from the first boot. The
interesting engineering is the set of fixes that make code-server and its
webviews render correctly when served same-origin behind the workspace's
path-rewriting proxy.

This repository is a published **minds inspiration**: a clean, bootable
snapshot of the apps and features a mind built, ready to adapt into your own.
It is NOT the generic workspace template -- it is this specific project.

## Use it

- **Create a new mind from it:** point a new minds workspace at this repo's
  URL. On first boot the mind reads the inspiration and helps you connect your
  own accounts and adapt it.
- **Bring it into an existing mind:** run `/use-inspiration <this repo's URL>`.

## What's inside

- **VS Code Web for Lean** -- [`inspiration-vscode-web-lean.md`](inspiration-vscode-web-lean.md) (published now)

Each `inspiration-<slug>.md` is the full manifest for that inspiration: what
it is, how it works, the prerequisites it needs, and how to adapt it.
