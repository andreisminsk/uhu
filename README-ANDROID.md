# uhu on Android (Termux)

Installation guide for running uhu on an Android phone via [Termux](https://termux.com), based on a real installation on aarch64 / Android 14 / Python 3.13.

## Requirements

- Android phone with a 64-bit CPU (aarch64 — any modern device)
- ~1.5 GB free space: Python toolchain ~620 MB, Rust ~590 MB, plus pip packages
- A free [ollama.com](https://ollama.com) account — for cloud models
- Wi-Fi recommended (total downloads ~300 MB)

## 1. Install Termux

Install Termux from [Google Play](https://play.google.com/store/apps/details?id=com.termux), [F-Droid](https://f-droid.org/en/packages/com.termux/), or [GitHub](https://github.com/termux/termux-app). All work fine; the Play Store version may receive updates a bit slower than the others.

## 2. Install packages

```
pkg update && pkg upgrade
pkg install ollama git python rust clang make pkg-config
```

> **Why rust?** Several pip dependencies (`pydantic-core` via `ollama`, `jiter` via `openai`) have no prebuilt Android wheels and compile from source on-device. Without rust, `pip install` fails with:
> `Target triple not supported by rustup: aarch64-unknown-linux-android`
>
> Install the toolchain **up front** — this avoids a failed install attempt halfway through (learned the hard way).

`python` pulls the full build chain (clang, llvm, make, pkg-config) automatically — ~105 MB download, ~620 MB disk.

## 3. Start Ollama and pull models

Unlike desktop, Termux does not run Ollama as a background service — start it manually **in a separate Termux session** (swipe from the left edge to open the session drawer, or tap `+` for a new one):

```
ollama serve
```

Leave it running in the foreground there — do **not** background it with `&`. Switch back to your main session to continue. (If `ollama list` already responds, the server is running.)

**Cloud models are recommended on phones** — local inference is slow on mobile hardware, while cloud models run on ollama.com infrastructure:

```
ollama pull glm-5.3-flash:cloud
ollama pull glm-5.2:cloud
ollama pull glm-5.3:cloud
```

Cloud model "pulls" download only a tiny manifest (~300 B) — the model itself runs remotely.

## 4. Sign in for cloud models

```
ollama run glm-5.3-flash:cloud
```

The first run asks you to sign in at `https://ollama.com/connect?...` — open the URL in your browser (Termux can't always open it automatically). After authenticating once, you'll see:

```
Connecting to 'glm-5.3-flash:cloud' on 'ollama.com' ⚡
```

Type `/exit` to leave the Ollama shell.

## 5. Install uhu

```
git clone https://github.com/andreisminsk/uhu
cd uhu
pip install -e .
```

The base install is minimal (`ollama`, `requests`, `prompt_toolkit`, `setproctitle`). Expect a few minutes of on-device compilation (`pydantic-core`, `setproctitle` — and `jiter` if you add the `openai` extra).

Optional extras:

```
pip install -e ".[search]"     # web search (ddgs)
pip install -e ".[openai]"     # OpenAI-compatible API (--api-openai)
pip install -e ".[all]"        # everything
```

> **Note:** skip the `[browser]` extra — Playwright/Chromium has no Android build and is not usable in Termux.

No virtualenv needed: Termux's Python is already isolated from Android itself (its own prefix under `/data/data/com.termux`), so installing into it directly is fine and simpler.

## 6. Create a workspace and run

```
mkdir ~/SANDBOX
cd ~/SANDBOX
uhu
```

You should see:

```
Connected | API: ollama | http://localhost:11434 | Model: glm-5.3-flash:cloud | Context: 1024000 | Stream: True | Agent: True | Tools: True | ...
Platform: android | Shell: bash/sh
```

## 7. Updating

```
cd ~/uhu
git pull
pip install -e .
```

Then restart uhu. (Use plain `git pull` — `git pull .` fetches from the local repo and does nothing.) The startup banner shows update notices automatically: `[⚠ Update available: v1.7.1 → v1.7.2. Run 'git pull' to update.]`

## Android-specific tips

- **Narrow terminal:** the thinking preview auto-fits the terminal width — rotate your phone and the display adapts live, no restart needed.
- **Keep Termux alive:** Android may kill background processes. While using uhu, acquire a wake lock: `termux-wake-lock` (release with `termux-wake-unlock`). Also disable battery optimization for Termux in Android settings.
- **Two sessions help:** keep `ollama serve` in one Termux session (swipe from the left edge to open the session drawer) and run `uhu` in another.
- **Context size:** the default `--ctx 1024000` works fine with cloud models — the phone only holds the conversation, not the model.
