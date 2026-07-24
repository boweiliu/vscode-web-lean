- Bumped the pinned Claude Code version from 2.1.207 to 2.1.219 (`Dockerfile`,
  `scripts/setup_system.sh`, and the `[agent_types.claude].version` pin in
  `.mngr/settings.toml`). The three must move together or the provisioning-time
  version check refuses to start the agent.

- Dropped `CLAUDE_CODE_ENABLE_OPUS_4_7_FAST_MODE=1` from `host_env__extend` in
  `.mngr/settings.toml`. That variable no longer exists in 2.1.219, and fast
  mode on Opus 4.7 has been removed upstream — the eligible models are now Opus
  4.8 and Opus 5. Current Claude Code enables fast mode by default for eligible
  models, gated only on the first-party API path plus the opt-out
  `CLAUDE_CODE_DISABLE_FAST_MODE` (left unset) and an org check that
  `CLAUDE_CODE_SKIP_FAST_MODE_ORG_CHECK=1` already bypasses.

  Motivation: in the OpenHost deployment, `fastMode = true` was inert —
  workspace requests carried no `speed: "fast"` parameter at all, so agents ran
  at standard speed on Opus 4.8 despite the setting. The 4.7-era capability gate
  is the suspected cause. Verify after deploying: the LLM gateway logs each
  request's params, and `speed: "fast"` should now appear alongside
  `reasoning.effort`.
