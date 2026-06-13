# Agent Memory

## Model Testing

- Whenever performing a model compatibility test, always append (do not overwrite!!!) the results to `MODELS-TEST.md`.
- The `model_test` tool now writes results to a temp file by default (or a path specified via `report_path` param). It does NOT touch `MODELS-TEST.md`. After running model_test, read the temp report file and APPEND its content to `MODELS-TEST.md`.
- Never discard individual per-test detail tables (test name, result, time). Every model entry must preserve its full detail section. Summary-only entries are unacceptable.
- When restoring lost data, check `.uhu/.cache/` for previous versions and `git show HEAD:<file>` for the last committed version.

## Windows UTF-8 encoding

- On Windows with non-English locales, `sys.stdout` defaults to a legacy codepage (e.g. cp1251, cp1252) that cannot encode emoji or non-Latin characters. This causes `UnicodeEncodeError: 'charmap' codec can't encode character`.
- **Always** add `sys.stdout.reconfigure(encoding='utf-8')` before any `print()` or `json.dump()` calls in Python scripts that may output Unicode (emoji, non-ASCII text, etc.).
- Alternatively, set the environment variable `PYTHONUTF8=1` to force UTF-8 mode globally.

## Android build environment

- **DO NOT** set `JAVA_HOME` inline in `cmd` (e.g. `set JAVA_HOME=...;`) — the space in `Program Files` and `;`-separated path semantics break parsing. Use the `android_build` tool or generate a script via `action=script`.
- Verified working on 2026-05-10 with Gradle 8.11.1, `compileDebugKotlin` task, JDK 21.0.10.

