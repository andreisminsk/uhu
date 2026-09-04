---
name: disk-toolkit
version: 1.0
description: Disk space inspection — scan, analyze, compare, and track disk usage over time. Uses pre-installed disk-scan and disk-stats CLI tools.
triggers:
  - disk space
  - disk usage
  - disk scan
  - scan disk
  - where is my disk space
  - disk space going
  - disk stats
  - disk toolkit
  - largest directories
  - biggest folders
  - disk growth
  - disk waste
  - free space
  - drive space
---

# Disk Toolkit

Disk space inspection toolkit with scan history and comparative analysis. Find where your disk space goes, track growth over time, and identify waste.

## Prerequisites

The `disk-scan` and `disk-stats` console scripts must be installed and on PATH. Verify with:

```
disk-scan --version
disk-stats --version
```

If not installed, the user should run `pip install -e .` or `pip install disk-toolkit` in the tool's source directory. Do NOT attempt to install it yourself unless explicitly asked.

## Activation

Triggered when the user asks about disk space, disk usage, largest directories, disk growth, disk waste, drive free space, or wants to scan/analyze the filesystem.

## Tools

Two CLI commands are available:

- **`disk-scan`** — scan filesystem and store results in SQLite (`~/.disk-toolkit/scans.db`)
- **`disk-stats`** — analyze and compare stored scans

## Workflow

1. **Understand the user's intent** — do they want to scan, analyze, compare, or find waste?
2. **Run the appropriate CLI command** using a RUN block.
3. **Present results** in a clear, readable format — tables or bullet lists.
4. **Suggest follow-ups** when relevant (e.g., drill deeper, compare scans, increase depth).

## Commands Reference

### Scanning

```bash
# Scan a directory (default max-depth: 10)
disk-scan run C:\Users\YourName

# Scan with deeper traversal for accuracy
disk-scan run C:\Users\YourName --max-depth 20

# Scan with a tag for later filtering
disk-scan run /home/user --max-depth 5 --tag monthly

# Scan multiple paths
disk-scan run /data /backup --tag weekly

# Delete scans older than 90 days (dry run first!)
disk-scan prune --dry-run --older-than 90
disk-scan prune --older-than 90
```

> ⚠️ **--max-depth** (default: 10) limits traversal depth. Directories deeper than this are skipped entirely — their files are NOT counted. If results don't match Windows Explorer, increase depth (20 for more accurate, 50 for near-complete).

### Analysis

```bash
# Top 20 largest directories
disk-stats top

# Top 10 photo directories
disk-stats top --category photos --top 10

# Top directories over 1GB
disk-stats top --min-size 1GB

# Top directories under a specific path
disk-stats top --path /home/user/Pictures --top 10

# Top directories with depth limit
disk-stats top --path /home/user --depth 2

# Drill into subdirectories
disk-stats ls --path /home/user/Pictures

# Drill with depth (children + grandchildren)
disk-stats ls --path /home/user/AppData/Local --depth 2

# Drill filtered by category
disk-stats ls --path /home/user --category llm
```

> ⚠️ **--min-size** (default: 100MB) excludes small directories from `top` results. Use `--min-size 0` to see everything:
> `disk-stats top --path C:/ --depth 1 --min-size 0 --top 30`

### Comparison & Trends

```bash
# Compare two scans — show growth/decline
disk-stats diff --path /home/user

# Compare specific category
disk-stats diff --path /home/user --category llm

# Find directories that grew >5% between scans
disk-stats waste --threshold 5

# Show new, grown, and shrunk directories since last scan
disk-stats recent

# Recent changes filtered by category
disk-stats recent --category llm

# Growth trends over 30 days
disk-stats trend --days 30
```

### File Types & History

```bash
# File type breakdown for a directory
disk-stats types --path /home/user/Pictures

# List all stored scans
disk-stats history

# Show drive free space history across scans
disk-stats drives

# List all available tags
disk-stats tags
```

### Tag Filtering

All `disk-stats` commands support `--tag` to filter by scan tag:

```bash
disk-stats top --tag monthly
disk-stats diff --tag monthly
disk-stats recent --tag monthly
disk-stats history --tag monthly
```

## Categories

Files are classified into categories based on extension and path. Path hints take priority over extensions.

| Category | Key Extensions | Path Hints |
|----------|--------------|------------|
| photos | .jpg .jpeg .png .heic .raw .tiff .webp .avif .cr2 .nef .arw .dng | photos pictures camera dcim lightroom |
| videos | .mp4 .mov .avi .mkv .wmv .m4v .webm | videos movies films |
| llm | .gguf .bin .safetensors .pt .onnx .h5 | models ollama huggingface llama checkpoints |
| browser-cache | (none) | google/chrome mozilla/firefox microsoft/edge cache_storage gpu cache code cache |
| dev | .py .js .ts .go .rs .java .cpp .h | node_modules .git venv __pycache__ target build android |
| games | (none) | warthunder steam steamapps epic games gog galaxy minecraft |
| appdata | (none) | appdata/roaming appdata/local |
| system | .dll .sys .exe .so .dylib .cache | windows program files programdata library |
| archives | .zip .tar .gz .7z .rar .dmg .iso | — |
| other | (everything else) | — |

## Drive Space Tracking

Each scan captures total and free space of the scanned drive:
- `disk-stats history` shows drive usage per scan (e.g. `410.4 GB/475.8 GB (86%)`)
- `disk-stats drives` shows a dedicated table of free space changes across scans

## Common Pitfalls

1. **Missing directories in results** — two causes:
   - `--min-size` filter (default 100MB) excludes small dirs. Use `--min-size 0` to see all.
   - Hidden/system directories (System Volume Information, $Recycle.Bin, Recovery) are skipped — they need admin privileges. Suggest running from an elevated terminal.
2. **Sizes smaller than expected** — increase `--max-depth` (default 10 may miss deeply nested data like browser caches, app data).
3. **No scans to compare** — `diff`, `waste`, `recent`, `trend` require at least 2 scans. Suggest running a scan first.
4. **Database location** — scan data is stored in `~/.disk-toolkit/scans.db` (SQLite), created automatically on first scan.

## Guidelines

- ALWAYS use RUN blocks to execute `disk-scan` and `disk-stats` commands — never try to query the database directly.
- **Scan timeout**: `disk-scan run` can take a long time on large directory trees. ALWAYS set a 5-minute (300s) timeout when running scan commands, e.g. using the `timeout` parameter in the RUN block. If a scan times out, suggest narrowing the path or reducing `--max-depth`.
- For first-time users, suggest running `disk-scan run <path>` before analysis commands.
- When presenting `top` results, format as a readable table or sorted list with sizes.
- When presenting `diff` or `recent` results, highlight growth/decline clearly.
- If a command fails, check whether the tools are installed (`disk-scan --version`) and report the error.
- Suggest tagging scans (e.g. `--tag monthly`) for meaningful comparative analysis over time.
- On Windows, use `cmd` or `powershell` as the RUN fence language.
