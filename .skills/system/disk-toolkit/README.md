# Disk Toolkit

Disk space inspection toolkit with scan history and comparative analysis. Find where your disk space goes, track growth over time, and identify waste.

## Requirements

- Python 3.10+
- [Click](https://click.palletsprojects.com/) (installed automatically)

## Installation

### Editable install (development)

Clone the repo and install in editable mode — changes to source are live immediately:

```bash
cd disk-toolkit
pip install -e .
```

This creates two console scripts on your PATH:

- `disk-scan` — scan filesystem and store results
- `disk-stats` — analyze and compare stored scans

### Verify installation

```bash
disk-scan --version
disk-stats --version
```

### Uninstall

```bash
pip uninstall disk-toolkit
```

### Build a distributable package

```bash
pip install build
python -m build
```

This produces `dist/disk_toolkit-0.1.0-py3-none-any.whl` and `dist/disk_toolkit-0.1.0.tar.gz`.

Install from the wheel:

```bash
pip install dist/disk_toolkit-0.1.0-py3-none-any.whl
```

## Usage

### Scan disk usage

> ⚠️ **Important:** The `--max-depth` parameter (default: 10) limits how deep the scanner traverses into subdirectories. Directories deeper than this limit are **skipped entirely** — their files are not counted. This means reported sizes will be **smaller than actual** if important data lives in deeply nested folders (e.g., browser caches, app data). If your stats don't match what Windows Explorer shows, increase the depth:
>
> ```bash
> disk-scan run C:\Users\YourName --max-depth 20   # more accurate
> disk-scan run C:\Users\YourName --max-depth 50   # near-complete
> ```

```bash
# Scan your home directory
disk-scan run C:\Users\YourName

# Scan with depth limit and tag
disk-scan run /home/user --max-depth 5 --tag monthly

# Scan multiple paths
disk-scan run /data /backup --tag weekly

# Delete scans older than 90 days (dry run first)
disk-scan prune --dry-run --older-than 90
disk-scan prune --older-than 90
```

### Analyze results

```bash
# Top 20 largest directories
disk-stats top

# Top 10 photo directories
disk-stats top --category photos --top 10

# Top directories over 1GB
disk-stats top --min-size 1GB

# Top directories under a specific path
disk-stats top --path /home/user/Pictures --top 10

# Drill into subdirectories of a path
disk-stats ls --path /home/user/Pictures

# Drill into subdirectories with depth (children + grandchildren)
disk-stats ls --path /home/user/AppData/Local --depth 2

# Drill into subdirectories, filtered by category
disk-stats ls --path /home/user --category llm

# Top directories with depth limit
disk-stats top --path /home/user --depth 2

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

# Show growth trends over 30 days
disk-stats trend --days 30

# Show file type breakdown for a directory
disk-stats types --path /home/user/Pictures

# List all stored scans
disk-stats history

# Show drive free space history across scans
disk-stats drives
```

### Tag filtering

All `disk-stats` commands support `--tag` to filter by scan tag:

```bash
# Only consider scans tagged 'monthly'
disk-stats top --tag monthly
disk-stats diff --tag monthly
disk-stats recent --tag monthly

# List scans with a specific tag
disk-stats history --tag monthly

# List all available tags
disk-stats tags
```

## Categories

Files are classified into categories based on extension and path:

| Category | Extensions | Path hints |
|----------|-----------|------------|
| photos | .jpg, .jpeg, .png, .heic, .raw, .tiff, .webp, .avif, .cr2, .cr3, .nef, .arw, .dng, .orf, .rw2 | photos, pictures, camera, dcim, lightroom |
| videos | .mp4, .mov, .avi, .mkv, .wmv, .m4v, .webm | videos, movies, films |
| llm | .gguf, .bin, .safetensors, .pt, .onnx, .h5 | models, ollama, huggingface, llama, checkpoints |
| browser-cache | (none) | google/chrome, mozilla/firefox, microsoft/edge, cache_storage, service worker, gpu cache, code cache |
| dev | .py, .js, .ts, .go, .rs, .java, .cpp, .h | node_modules, .git, venv, __pycache__, target, build, android |
| games | (none) | warthunder, steam, steamapps, epic games, gog galaxy, minecraft |
| appdata | (none) | appdata/roaming, appdata/local |
| system | .dll, .sys, .exe, .so, .dylib, .cache | windows, program files, programdata, library |
| archives | .zip, .tar, .gz, .7z, .rar, .dmg, .iso | — |
| other | (everything else) | — |

Path hints take priority over extensions — a `.bin` file in an `ollama/` directory is classified as `llm`, not `other`.

## Drive Space Tracking

Each scan captures the total and free space of the drive being scanned. This lets you observe disk space dynamics over time:

- `disk-stats history` shows drive usage per scan (e.g. `410.4 GB/475.8 GB (86%)`)
- `disk-stats drives` shows a dedicated table of free space changes across scans
- Older scans (before this feature) show `—` for drive info

## Notes & Limitations

> ⚠️ **Directories may appear missing from results!** There are two common reasons:
>
> 1. **`--min-size` filter (default: 100MB)** — Directories smaller than this threshold are excluded from `top` results. Use `--min-size 0` to see everything:
>    ```bash
>    disk-stats top --path C:/ --depth 1 --min-size 0 --top 30
>    ```
>
> 2. **Hidden / system directories are skipped** — `os.walk` silently skips directories it cannot read (e.g. `System Volume Information`, `$Recycle.Bin`, `Recovery`). These require admin privileges to list. Run the scan from an elevated (Administrator) terminal to include them.

## Database

Scan data is stored in `~/.disk-toolkit/scans.db` (SQLite). The database is created automatically on first scan.

## How it works

1. **disk-scan** walks the directory tree, classifies files by type, and stores aggregate sizes per directory in SQLite.
2. **disk-stats** queries the stored data to show top directories, compare scans, and identify waste trends.

Each scan is a snapshot. Run scans periodically (e.g., monthly) to enable comparative analysis.
