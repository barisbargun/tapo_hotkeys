# Tapo Hotkeys — Agent Instructions

## Project overview
- Windows keyboard shortcuts control a TP-Link Tapo L535E smart bulb over the local network.
- `TapoHotkeys.ahk` (AutoHotkey v2) launches the persistent Python service and atomically publishes command files to `pending/`.
- `tapo_service.py` uses `python-kasa==0.12.0` and `keyring` (Windows Credential Manager) to control the bulb.
- `Stop_Controller.ahk` publishes a STOP command; `setup_credentials.py` configures credentials; `test_tapo_service.py` contains hardware-free tests.
- `README.md` documents the supported Windows setup and shortcuts. Check it and the actual code before changing documented behavior.

## Communication
- Respond to the user in Turkish, concisely and clearly.
- Keep filenames, identifiers, commands, code, and user-facing English documentation in their appropriate original language.
- Prefer actionable summaries over long essays; distinguish confirmed findings from hypotheses.
- After changes, summarize modified files, tests and outcomes, untested scenarios, and any required Windows checks.

## Development rules
- Change only what the user requests. Prefer minimal, readable, maintainable changes; avoid unrelated refactoring or dependencies.
- Preserve existing shortcut mappings and functional behavior unless the user requests a change.
- Preserve the no-white-flash behavior: powering on with a color or brightness change should not briefly apply an unwanted default white state.
- Preserve low-latency startup, background connection warm-up, session reuse, bounded recovery, and safe shutdown.
- Keep one owner for device writes; avoid races and out-of-order state changes.
- Coalesce only consecutive, still-pending built-in color commands (7–9), preserving the latest color. Do not silently drop presets, power toggles, brightness steps, or STOP.
- Preserve sequential brightness clamping to 1–100% and correct power-toggle semantics; be careful with ambiguous timeouts and stale cached device state.
- Publish queue files atomically (write temporary file, then rename) and avoid replaying stale commands after connectivity failures.
- Keep Windows/AutoHotkey compatibility in mind. The launcher currently expects a user-installed Python 3.14 `pythonw.exe`; do not change that path without checking the user's environment.

## Security and privacy
- Never print, commit, or request that the user paste Tapo credentials, tokens, or secrets into source files or chat.
- Keep credentials in Windows Credential Manager through `setup_credentials.py`; do not remove this setup script from version control.
- Treat the hard-coded `HOST` value as local machine configuration. Do not expose additional network details in documentation or logs; do not overwrite the user's working IP without permission.
- Do not commit `pending/`, logs, temporary files, virtual environments, caches, or generated secrets. Review `git diff` before committing.

## Testing and environment
- Run the hardware-free Python test suite after relevant code changes: `python -m unittest -v test_tapo_service` (use the project's available Python interpreter).
- If dependencies are installed, also run `python -m pip check`.
- On Codex Cloud/Linux, use the configured virtual environment when available. Mock device discovery, keyring, and bulb operations; do not require physical hardware or real credentials.
- Do not claim Windows, AutoHotkey, startup-latency, or real-bulb behavior was verified unless it was actually tested.
- For device-facing changes, provide a short local Windows verification plan covering startup, rapid color presses, brightness bounds, toggle, offline recovery, and no-white-flash behavior.

## Git and releases
- Use a feature branch and pull request for functional code changes where practical.
- Do not merge into `main`, push unrelated changes, rewrite history, delete branches, create tags, or publish GitHub Releases unless the user explicitly asks.
- Do not alter repository visibility, description, topics, or licensing without the user's request.
- Never change a published release tag to point at a different commit without explicit approval.
