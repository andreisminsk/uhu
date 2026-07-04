#!/usr/bin/env python3
"""desc2dsl — Convert a natural language description into graphai-dsl2image DSL format using Ollama."""

import sys
import os
import re
import argparse

def load_env(env_path=None):
    """Load .env file into environment variables."""
    if env_path is None:
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if not os.path.exists(env_path):
        return
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
            if m:
                os.environ[m.group(1)] = m.group(2).strip().strip('"').strip("'")


def load_prompt(prompt_path=None):
    """Load the system prompt from GRAPH.md."""
    if prompt_path is None:
        prompt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'GRAPH.md')
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()


def call_ollama(description: str, model: str, base_url: str, api_key: str, prompt: str) -> str:
    """Call Ollama API (OpenAI-compatible /v1 endpoint) and return the generated DSL text."""
    import json, urllib.request, urllib.error

    # Use /v1/chat/completions (OpenAI-compatible) — more reliable than native API
    url = f"{base_url}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key and api_key != "ollama-local":
        headers["Authorization"] = f"Bearer {api_key}"

    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": description}
        ],
        "temperature": 0.1,
        "max_tokens": int(os.environ.get("LLM_MAX_TOKENS", "131072"))
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            msg = result.get("choices", [{}])[0].get("message", {})
            # Reasoning models (e.g. glm-5.1) may put output in "reasoning"
            # and leave "content" empty — fall back to reasoning if needed.
            return msg.get("content") or msg.get("reasoning") or ""
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"API error {e.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        print(f"Make sure Ollama is running at {base_url}", file=sys.stderr)
        sys.exit(1)


def clean_dsl(raw: str) -> str:
    """Extract DSL from model output, stripping markdown fences if present."""
    text = raw.strip()
    text = re.sub(r'^```[\w]*\n?', '', text)
    text = re.sub(r'\n?```$', '', text)
    lines = [line.rstrip() for line in text.splitlines()]
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Convert a natural language description to graphai-dsl2image DSL format."
    )
    parser.add_argument("input", help="Path to a .txt file with the description, or '-' for stdin")
    parser.add_argument("-o", "--output", help="Output .dsl file path (default: same name as input with .dsl extension)")
    parser.add_argument("-m", "--model", help="Ollama model to use (default: from .env MODEL)")
    parser.add_argument("--base-url", help="Ollama API base URL (default: from .env or http://127.0.0.1:11434)")
    parser.add_argument("--api-key", help="Ollama API key (default: from .env or ollama-local)")
    parser.add_argument("--prompt", help="Additional guidance to shift model focus (e.g. 'Structure based on Comparison by Use Case table')")
    parser.add_argument("--prompt-file", help="Path to prompt file (default: GRAPH.md)")
    parser.add_argument("--raw", action="store_true", help="Print raw model output without cleanup")
    args = parser.parse_args()

    load_env()

    model = args.model or os.environ.get("MODEL", "glm-5.1:cloud")
    base_url = args.base_url or os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    base_url = re.sub(r'/v1$', '', base_url)  # Strip /v1 since we add it in call_ollama
    api_key = args.api_key or os.environ.get("OLLAMA_API_KEY", "ollama-local")

    # Load description
    if args.input == '-':
        description = sys.stdin.read()
    else:
        with open(args.input, 'r', encoding='utf-8') as f:
            description = f.read()

    # Load prompt
    prompt = load_prompt(args.prompt_file)

    # Append user-provided focus guidance
    if args.prompt:
        prompt += f"\n\n## Additional Guidance\n\n{args.prompt}\n\nFollow this guidance to adjust the structure and focus of the DSL output. It overrides the default approach in this prompt where they conflict."

    # Call model
    print(f"Calling {model}...", file=sys.stderr)
    raw_output = call_ollama(description, model, base_url, api_key, prompt)

    if args.raw:
        print(raw_output)
        return

    dsl = clean_dsl(raw_output)

    # Output
    if args.output:
        out_path = args.output
    elif args.input != '-':
        base = os.path.splitext(os.path.basename(args.input))[0]
        out_path = os.path.join(os.getcwd(), base + '.dsl')
    else:
        out_path = None

    if out_path:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(dsl + '\n')
        print(f"DSL saved to: {out_path}", file=sys.stderr)
    else:
        print(dsl)

    # Validate
    lines = [l.strip() for l in dsl.splitlines() if l.strip() and not l.startswith('#')]
    if not lines:
        print("Warning: No DSL lines generated!", file=sys.stderr)
    else:
        node_count = sum(1 for l in lines if re.match(r'^\w+\s+"', l))
        print(f"Generated {node_count} nodes, {len(lines)} lines", file=sys.stderr)


if __name__ == '__main__':
    main()