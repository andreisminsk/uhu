**This repository is Read-Only.** 
This project is publicly visible for educational or reference purposes

Project demo video: https://youtu.be/heG0QWUt4Lw

# ollama-chat-agentic

**uhu** (nickname) is a minimalistic agentic coder that lets you closely interact with the model and see how the agentic flow works under the hood. No magic — just a transparent feedback loop of actions, observations, and model calls you can watch unfold step by step. Unlike common agentic coders, uhu focuses on conservative context consumption, helping you achieve the most productive use of tokens. Switch between models with `--model` to compare how different LLMs — small or large, local or cloud — behave in their natural agentic habitat. You can also connect to remote Ollama instances with `--host` (e.g. a Mac Mini M4 Pro running `gemma4:31b` on your local network at `--host http://192.168.1.42:11434`), so you are able to explore and make your own assessment of conversation capabilities of local models. uhu also supports custom skills — reusable, composable workflows you define in JSON that extend the model's capabilities for specific tasks.

## Features

- **Agent mode** (`--agent`): Parse and execute WRITE/EDIT/RUN/FILE blocks from model output
- **Tools mode** (on by default, `--no-tools` to disable): 20 structured tool calls for filesystem, git, HTTP, browser automation, and more
- **Skills mode** (`--skills` - off by default): Invoke development skills (code-review, test-gen, doc-gen, plan, md2pdf, what-if, root-cause, problem-solving, architect, medicine, business-coach, pro-bidder) and custom skills
- **Streaming support** (`--stream`): Token-by-token output
- **Session persistence**: Save/restore conversations with `/save` and `/restore`
- **Auto-compaction**: `/compact` summarizes history to free context
- **Permanent memory**: `/memorize` saves instructions/facts across sessions via PROJ-MEMORY.md and AGENT-MEMORY.md
- **File caching**: Previous versions saved to `.uhu/.cache/` for diff review
- **In-memory rollback**: Auto-restore files on WRITE/EDIT failures
- **Batch write limit**: Pauses after 3 file changes per round for review
- **Thinking mode** (`--thinking`): Handle thinking tokens from reasoning models (qwen3, deepseek-r1)
- **Browser automation** (on by default with tools): Playwright-based browser with stealth support for scraping and interaction

## Installation

1. **Install Python 3.10 or later**
   
   - Download from [python.org](https://www.python.org/downloads/)
   - On Windows, check "Add Python to PATH" during installation
   - Verify: `python --version`

2. **Install Ollama**
   
   - Download from [ollama.ai](https://ollama.ai) and follow the installer
   - After installation, Ollama runs as a background service
   - Verify: `ollama list` (should show installed models, or an empty list)
   - Pull a model: `ollama pull glm-5.1:cloud` (or any model you prefer)
   - Verify Ollama is running: `curl http://localhost:11434/api/tags` 
   - Verify that model was deployed successfully: `ollama run glm-5.1:cloud` 
   - Check your model's context window size for the `--ctx` parameter (e.g. [glm-5.1](https://ollama.com/library/glm-5.1) specifies 198K → `--ctx 202752` since 198 × 1024 = 202752)

3. **Clone this repository**
   Assume that you are planning to put the tool into e.g. `~/Projects/` foder, then:
   
   ```
   cd ~/Projects
   git clone https://github.com/andreisminsk/uhu.git
   cd uhu
   ```

4. **Create a virtual environment** (macOS/Linux)
   Open a terminal in the `uhu` folder (e.g. `~/Projects/uhu`), then:
   
   ```
   python3 -m venv venv
   source venv/bin/activate
   ```
   
   On subsequent sessions, just run `source venv/bin/activate` before starting uhu.

5. **Install Python dependencies**
   
   ```
   pip install -r requirements.txt
   ```

6. **Optional — Browser automation**
   
   ```
   pip install playwright playwright-stealth
   playwright install chromium
   ```

7. **Optional — Google Calendar integration**
   
   ```
   pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
   ```

8. **Optional — Markdown to PDF conversion (md2pdf skill)**
   
   ```
   pip install markdown pymdown-extensions xhtml2pdf
   ```

## Quick Launch

### Windows

Create a batch file on your PATH (e.g. `C:\Users\<you>\.uhu\uhu.bat`):

```
@python "C:\Users\\<you>\Projects\uhu\ollama_agent.py" %*
```

Add its directory to your PATH, then from any working directory:

```
uhu
uhu --model qwen2.5:14b --ctx 32768
uhu --no-agent --no-tools
```

### macOS / Linux

Create a shell script on your PATH (e.g. `~/.local/bin/uhu`):

```
#!/bin/sh
~/Projects/uhu/venv/bin/python ~/Projects/uhu/ollama_agent.py "$@"
```

Make it executable:

```
chmod +x ~/.local/bin/uhu
```

Ensure `~/.local/bin` is on your PATH (add to `~/.bashrc` or `~/.zshrc` if needed):

```
export PATH="$HOME/.local/bin:$PATH"
```

Then from any working directory:

```
uhu
uhu --model qwen2.5:14b --ctx 32768
uhu --no-agent --no-tools
```

## Quick Start

1. **Create a working folder** for your new project:
   
   ```
   mkdir my-project && cd my-project
   ```

2. **Open a terminal in that folder and run ``uhu``**:
   
   ```
   uhu
   ```

The tool launches and connects to Ollama.

3. **Type your prompt** — start a discussion about your project idea or start building at once:

> *I want to build a Python Telegram bot that reads some Telegram groups for me and gives me a summary so I don't need to waste time on it. How to approach this?*

> *Let's build a simple Arduino project — a HelloWorld app that blinks 3 LEDs in sequence and writes output to Serial.*

> *I have an idea for an Android app — it should get my heart rate and stress level data over time from an Android SmartWatch. Let's ideate how to approach this.*

uhu will respond, execute actions, and loop through up to 3 feedback rounds automatically. When it pauses, give it feedback or a new direction.

## Usage

### Basic chat

Agent, tools, streaming, thinking enabled by default:

```
uhu
```

or: 

```
python ollama_agent.py
```

### One-shot mode (non-interactive)

Execute a single prompt with full feedback loop (7 rounds) and exit. No banner, no interactive input. All actions are auto-approved.

```
uhu "What does this project do?"
uhu --model qwen2.5:14b "Summarize README.md"
uhu --skills "Review src/app.py"
```

or:

```
python ollama_agent.py "What does this project do?"
```

### Disable agent mode

```
uhu --no-agent
```

or: 

```
python ollama_agent.py --no-agent
```

### Enable skills (disabled by default)

```
uhu --skills
```

### Custom model and context size

Refer to model specifications at Ollama web site to set max context size. Example: [glm-5.1:cloud](https://ollama.com/library/glm-5.1) specifies 198K → `--ctx 202752` since 198 × 1024 = 202752

```
uhu --model glm-5.1:cloud --ctx 202752
```

### Disable streaming output

```
uhu --no-stream
```

### Specify working directory

By default, working directory is the one from which ``uhu`` was called

```
uhu --workdir /path/to/project
```

### Disable autosave and file caching

The tool saves sessions in ``.uhu/.sessions`` folder so that user can restore them using /restore command

```
uhu --no-autosave --no-cache
```

## Command-line Options

| Option            | Default                    | Description                                                              |
| ----------------- | -------------------------- | ------------------------------------------------------------------------ |
| `prompt`          | —                          | One-shot prompt — execute and exit (7 feedback rounds, auto-approve all) |
| `-v`, `--version` | —                          | Show version and exit                                                    |
| `--host`          | `http://localhost:11434`   | Ollama server URL                                                        |
| `--model`         | `glm-5.1:cloud`            | Model name                                                               |
| `--ctx`           | `202752`                   | Context window size in tokens                                            |
| `--no-stream`     | off (streaming on)         | Disable streaming output                                                 |
| `--no-log`        | off (logging on)           | Disable conversation logging                                             |
| `--sessions-dir`  | `<workdir>/.uhu/.sessions` | Directory for saved sessions                                             |
| `--no-agent`      | off (agent on)             | Disable agentic coder mode                                               |
| `--workdir`       | `.`                        | Working directory for file operations                                    |
| `--no-tools`      | off (tools on)             | Disable structured tool calls                                            |
| `--skills`        | off                        | Enable skill invocations                                                 |
| `--skills-dir`    | `./.skills`                | Custom skill definitions directory                                       |
| `--no-autosave`   | off                        | Disable automatic session saving                                         |
| `--no-thinking`   | off (thinking on)          | Disable thinking mode for reasoning models                               |
| `--mcp`           | off                        | Enable MCP server tools (configured in `.ollama_agent.json`)             |
| `--no-cache`      | off                        | Disable file caching to `.uhu/.cache/` directory                         |

## Slash Commands

| Command                            | Description                                                                                                                                                  |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `/help`                            | Show available commands                                                                                                                                      |
| `/reset`                           | Clear conversation history (keeps system prompt)                                                                                                             |
| `/v`, `/ver`, `/version`           | Show version (also `-v` CLI flag)                                                                                                                            |
| `/history`                         | Show context usage bar                                                                                                                                       |
| `/sober`                           | Re-inject system prompt to refocus the model. Use it when you see that model becomes inadequate, but you want to preserve context and continue conversation. |
| `/compact`                         | Summarize history into a compact briefing                                                                                                                    |
| `/compact memory [project\|agent]` | Compact memory file using LLM deduplication                                                                                                                  |
| `/memorize <text>`                 | Add entry to project memory (auto-classified)                                                                                                                |
| `/memorize project <text>`         | Add entry to project memory (PROJ-MEMORY.md)                                                                                                                 |
| `/memorize agent <text>`           | Add entry to agent memory (AGENT-MEMORY.md)                                                                                                                  |
| `/auto`                            | Toggle auto-all mode / show approval settings                                                                                                                |
| `/auto reset`                      | Clear session auto-approvals                                                                                                                                 |
| `/auto reset always`               | Clear persistent (always) approvals                                                                                                                          |
| `/auto reset all`                  | Clear both session and persistent approvals                                                                                                                  |
| `/diff`                            | Toggle auto-diff for edits                                                                                                                                   |
| `/m` or `/multiline`               | Enter multiline mode                                                                                                                                         |
| `/attach <path>`                   | Attach file(s) to next message                                                                                                                               |
| `/attach-bin <path>`               | Attach binary file reference                                                                                                                                 |
| `/search <pattern> <glob>`         | Search across files                                                                                                                                          |
| `/peek <path>`                     | Show head+tail of a file                                                                                                                                     |
| `/ls [path]`                       | List directory contents                                                                                                                                      |
| `/md <path>`                       | Create a directory                                                                                                                                           |
| `/skills`                          | List available skills                                                                                                                                        |
| `/save [name]`                     | Save session                                                                                                                                                 |
| `/restore [name]`                  | Restore a saved session                                                                                                                                      |
| `/sessions`                        | List all saved sessions                                                                                                                                      |
| `exit` / `/exit` / `/bye`          | Exit the session                                                                                                                                             |

## Confirmation Options

When the agent wants to perform an action, you are prompted:
 [WRITE] app.py (42 lines) (y/N/auto/all/always/d):

| Option   | Effect                              | Scope                                |
| -------- | ----------------------------------- | ------------------------------------ |
| `y`      | Approve this one action             | One-time                             |
| `N`      | Deny this action                    | One-time                             |
| `auto`   | Auto-approve this file/command      | Current session                      |
| `all`    | Auto-approve everything             | Current session                      |
| `always` | Auto-approve in all future sessions | Persistent (`.uhu/coderconfig.json`) |
| `d`      | Show diff/details before deciding   | One-time                             |

Persistent approvals are saved to `.uhu/coderconfig.json` in the project directory and loaded automatically on startup.

## Feedback Loop

When agent/tools/skills mode is active, the model's response may contain actions (WRITE, EDIT, RUN, TOOL, etc.). After executing them, the model is called again to process the results — this is the **feedback loop**. Up to 3 rounds are executed automatically.

The loop is intentionally limited to 3 rounds to keep the coding flow under control and the user attached to the process of creation. After 3 rounds, uhu asks for at least minimal user feedback before continuing — preventing the model from spiraling off on its own. You can also interrupt any round with **Ctrl+C**.

How it works:

1. **Round 1**: The model responds. Actions are parsed and executed. Observations are collected.
2. **After execution**, the loop checks what happened:
- **Actions produced observations** → model is called again to process results (`⟳ Round X/Y — model continuing...`)
- **Read-only actions only** (FILE: blocks) → model is called again, but tracked as a read-only round (`⟳ Round X/Y (reading)`). After 3 consecutive read-only rounds, the loop stops.
- **No actions at all** → the model may be stuck describing intent. A nudge is injected and the model is called again (`⟳ Round X/Y — nudging model...`)
3. **Loop detection**: If the same action signature repeats across rounds (e.g. same EDIT on same file), it's blocked and a loop warning is injected.
4. **Last round (3/3)**: Nudging is skipped — there's no point calling the model again since the loop ends. Instead, `_nudge_if_stuck` is still evaluated to determine the exit message: if the model is stuck, it falls through to `⚠ Max feedback rounds reached`; if genuinely done, it prints `✓ Done — no more actions`. Remaining actions are still processed, but the model isn't called back.
5. **Termination**: The loop ends when:
- The model produces no actions and no nudge is needed (`✓ Done`)
- Max rounds exhausted (3 by default)
- 3 consecutive read-only rounds
- User interrupts (Ctrl+C)
- An error occurs

Status indicators show what's happening:

| Indicator                                                   | Meaning                                        |
| ----------------------------------------------------------- | ---------------------------------------------- |
| `⟳ Round 2/3 — model continuing...`                         | Model produced actions, continuing             |
| `⟳ Round 2/3 (reading) — model is gathering information...` | Read-only round (FILE: blocks only)            |
| `⟳ Round 2/3 — nudging model...`                            | Model described intent but produced no actions |
| `✓ Done — no more actions`                                  | Model finished naturally                       |
| `⊘ Cancelled`                                               | User cancelled a RUN command                   |
| `⚠  Stopped after 3 read-only rounds`                       | Model kept reading without acting              |
| `⚠  Max feedback rounds (3) reached`                        | Loop limit hit — send a message to continue    |

On the last feedback round (e.g. Round 3/3), nudging is skipped — the loop is about to end, so a system nudge would be wasted. This is the point where **user input is needed** to unblock the model. Send a message to continue or redirect the conversation.

The `/sober` command re-injects the system prompt to refocus a drifting model. It's also called automatically after `/compact` to reinforce instructions.

## Context Conservation

| Limit                          | Value   | Purpose                                   |
| ------------------------------ | ------- | ----------------------------------------- |
| `MAX_OBSERVATION_CHARS`        | 4,000   | WRITE/EDIT/RUN status messages            |
| `MAX_READ_OBSERVATION_CHARS`   | 70,000  | FILE: reads (agent needs full source)     |
| `MAX_SKILL_OBSERVATION_CHARS`  | 1,500   | Skill/tool intermediate output            |
| `MAX_TOTAL_OBSERVATION_CHARS`  | 120,000 | Combined limit per action round           |
| `MAX_BATCH_WRITES`             | 3       | Max file changes per round before pausing |
| `MAX_FEEDBACK_ROUNDS`          | 3       | Max feedback loop iterations per message  |
| `MAX_IDENTICAL_ACTION_REPEATS` | 3       | Skip execution after this many repeats    |
| `LOOP_NUDGE_THRESHOLD`         | 2       | Warn after this many identical actions    |

## Permanent Memory

Permanent memory is a lightweight mechanism for storing instructions and ideas that guide the model across sessions. Think of it as a scratchpad for concepts in progress — an instruction stored here is meant to be tried out, and if it proves useful over time, it graduates into either a permanent product feature or a custom skill. Memory entries are not meant to accumulate forever; they are working notes that evolve or get replaced.

The agent supports two persistent memory files that are loaded into the system prompt every session:

| File              | Location                     | Scope                     |
| ----------------- | ---------------------------- | ------------------------- |
| `PROJ-MEMORY.md`  | Working directory            | Project-specific          |
| `AGENT-MEMORY.md` | Next to `.ollama_agent.json` | Agent-wide (all projects) |

Entries are auto-classified into five sections (priority order):

1. **Instructions** — Behavioral directives (highest priority)
2. **Preferences** — Style and format choices
3. **Conventions** — Project standards, naming, patterns
4. **Facts** — Important truths to remember
5. **Notes** — Miscellaneous

Project memory overrides agent memory on conflicts. Size warnings appear at 40 lines; capacity limit at 50 (configurable in `.ollama_agent.json`):

```json
{
  "memory": {
 "max_lines": 50,
 "warn_threshold": 40
  }
}
```

Use `/compact memory` to deduplicate and condense a memory file using the LLM.

## Tools

Available when running with tools enabled (default):

| Tool              | Auto-approve | Description                                                                                                            |
| ----------------- |:------------:| ---------------------------------------------------------------------------------------------------------------------- |
| `read_file`       | Yes          | Read file contents (cross-platform cat)                                                                                |
| `search_in_files` | Yes          | Regex search across files (cross-platform grep)                                                                        |
| `list_files`      | Yes          | List directory contents (cross-platform ls)                                                                            |
| `find_file`       | Yes          | Find files by glob pattern                                                                                             |
| `peek_file`       | Yes          | Show head+tail of a file                                                                                               |
| `file_link`       | Yes          | Generate file:// URL for a file                                                                                        |
| `env_info`        | Yes          | System, Python, and package info; geolocation with `geo:true`                                                          |
| `mkdir`           | Yes          | Create directories (cross-platform)                                                                                    |
| `py_compile`      | Yes          | Check Python syntax, imports, run expressions                                                                          |
| `write_file`      | No           | Create/overwrite/append files                                                                                          |
| `replace_in_file` | No           | Surgical search/replace edits in files                                                                                 |
| `copy_file`       | No           | Copy files or directories                                                                                              |
| `move_file`       | No           | Move/rename files or directories                                                                                       |
| `run_command`     | No           | Execute shell commands with structured output                                                                          |
| `git`             | Yes          | Read-only git operations (status, diff, log)                                                                           |
| `web_search`      | No           | Search the web via DuckDuckGo                                                                                          |
| `web_fetch`       | No           | Fetch and extract web page content                                                                                     |
| `http_request`    | No           | Make HTTP requests (GET, POST, etc.)                                                                                   |
| `image_analysis`  | No           | Analyze images via Ollama vision model                                                                                 |
| `google_calendar` | No           | Manage Google Calendar events                                                                                          |
| `weather`         | Yes          | Weather forecast via wttr.in (no API key)                                                                             |
| `token_count`     | Yes          | Estimate token count for text or a file (chars/4, words×1.3, tiktoken)                                               |
| `llm_query`       | No           | Send prompts to a secondary LLM                                                                                        |
| `browser`         | No           | Playwright browser automation with stealth support (navigate, extract, screenshot, PDF, click, fill, scroll, evaluate) |

### Token Counting

The `token_count` tool estimates how many tokens a text or file will consume — useful for checking if content fits within a model's context window.

It provides three estimation methods:

| Method | How it works | Accuracy | Dependency |
|--------|-------------|----------|------------|
| `chars/4` | Characters ÷ 4 | Rough (~80%) | None |
| `words×1.3` | Word count × 1.3 | Rough (~85%) | None |
| `tiktoken` | OpenAI's BPE tokenizer | Exact | `pip install tiktoken` |

**tiktoken** is OpenAI's open-source tokenizer. It converts text into the actual tokens that LLMs process — the same algorithm used by GPT-4, GPT-3.5, and other models. Different models use different encodings:

- `cl100k_base` — GPT-4, GPT-3.5-turbo (default)
- `p50k_base` — Codex models
- `r50k_base` — GPT-3 (davinci)
- `o200k_base` — GPT-4o, GPT-4o-mini

The `chars/4` and `words×1.3` estimates work without any dependencies. For exact counts, install tiktoken: `pip install tiktoken`.

## MCP (Model Context Protocol)

Enable MCP server tools with `--mcp`. MCP servers are configured in `.ollama_agent.json` under `mcpServers`:

```json
{
  "mcpServers": {
    "mcp-imagineer": {
      "url": "http://localhost:18080/sse",
      "timeout": 120
    },
    "huggingface": {
      "url": "https://huggingface.co/mcp",
      "timeout": 120
    },
    "canva": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://mcp.canva.com/mcp"],
      "timeout": 120
    },
    "my-local-server": {
      "command": "my-mcp-server",
      "args": ["--port", "3000"],
      "env": { "API_KEY": "..." }
    }
  }
}
```

Three transport types are supported:
- **SSE** — URL ending with `/sse`: HTTP Server-Sent Events connection (e.g. `http://localhost:18080/sse`)
- **Streamable HTTP** — URL not ending with `/sse`: Direct JSON-RPC POST (e.g. `https://huggingface.co/mcp`)
- **stdio** — `command` field: Subprocess communication

Config options per server:
| Field | Required | Description |
|-------|----------|-------------|
| `url` or `command` | Yes | Server URL or executable |
| `timeout` | No | Request timeout in seconds (default: 120) |
| `auto_approve` | No | Auto-approve tool calls without confirmation (default: false) |
| `headers` | No | Custom HTTP headers (e.g. `{"Authorization": "Bearer ..."}`) |
| `args` | No | Arguments for stdio command |
| `env` | No | Environment variables for stdio command |

When `--mcp` is enabled, uhu connects to all configured servers in parallel at startup, discovers available tools, and registers them with prefixed names (e.g. `mcp_imagineer_generate_image`). The model can then invoke MCP tools using the standard `**TOOL:**` block format. Binary content (images) from MCP responses is automatically saved to the working directory.

```bash
uhu --mcp
uhu --mcp "Generate an image of a cat"
uhu --mcp --skills "Search HuggingFace for sentiment analysis models"
```

### HuggingFace MCP example

The HuggingFace MCP server provides tools for model, dataset, space, and paper search — useful for discovering models to pull into Ollama without leaving the terminal:

```bash
# Find the best coding model that fits 16GB memory
uhu --mcp
You: Find the best Qwen3 model for coding that fits 16GB unified memory
AI: [calls mcp_huggingface_model_search] → returns ranked list with sizes
You: Pull the top result
AI: [runs ollama pull qwen3:8b-q4_K_M]
```

Available HuggingFace tools: `model_search`, `dataset_search`, `space_search`, `paper_search`, `doc_search`, and image generation (anonymous tier).

### Canva MCP example

The Canva MCP server provides design creation and editing tools via OAuth (browser login on first connect):

```json
{
  "canva": {
    "command": "npx",
    "args": ["-y", "mcp-remote", "https://mcp.canva.com/mcp"],
    "timeout": 120
  }
}
```

Requires Node.js (`npx`) installed. On first connect, a browser window opens for OAuth login. After authentication, Canva tools like `create_design`, `get_asset`, and `search_brand` become available.

## Project Configuration

### CODERGUIDE.md

Place a `CODERGUIDE.md` file in your project directory to provide coding guidelines to the agent. 

### .uhu/coderconfig.json

Stores persistent auto-approval settings:
    {
      "always_writes": ["src/app.py"],
      "always_runs": ["python test.py"]
    }

### .skills/

Custom skill definitions - SKILL.md directories, Python (.py) or JSON (.json) files.

## License

This project is licensed under **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)**.

You are free to use, modify, and share this work for **non-commercial purposes only**, provided you:

- Give appropriate credit (attribution)
- Distribute derivatives under the same license (share-alike)

**Commercial use is not permitted** under this license. As the copyright holder, the author retains full commercial rights.

This project is AI-assisted — code was produced with the help of large language models under paid accounts. The license applies to the curated work as a whole, including human direction, review, and creative choices.

Full license text: [LICENSE](LICENSE) · https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode

**Disclaimer:** This project is provided "as is", without warranty of any kind, express or implied, including but not limited to warranties of merchantability, fitness for a particular purpose, and noninfringement. In no event shall the authors be liable for any claim, damages, or other liability arising from the use of this software.
