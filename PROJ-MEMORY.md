# Project Memory

## Changelog

- When a commit bumps the version in `uhu-ver.txt`, update `CHANGELOG.md` in the same commit: open a new `## [X.Y.Z] - YYYY-MM-DD` section, move entries from `## Unreleased` under it, newest first. Bump date = commit date.
- Commits that don't touch `uhu-ver.txt` accumulate under `## Unreleased` and roll into the next version section at the following bump.
