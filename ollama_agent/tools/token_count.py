"""Token count tool — estimate token count for text or a file."""


class TokenCountTool:
    name = "token_count"
    description = (
        "Estimate token count for text or a file. "
        "Returns character count, word count, line count, and token estimates "
        "(chars/4, words*1.3, and tiktoken cl100k if available)."
    )
    system_prompt = """## token_count

Estimate token count for text or a file. Useful for checking context window usage before sending content to a model.

Parameters (JSON object):
- text (string, optional): Text to count tokens for. Mutually exclusive with path.
- path (string, optional): Path to a file to read and count tokens for. Mutually exclusive with text.
- model (string, optional): Model encoding to use for tiktoken. Default: "cl100k_base". Options: "cl100k_base" (GPT-4/GPT-3.5), "p50k_base" (Codex), "r50k_base" (GPT-3). Only used if tiktoken is installed.

If neither text nor path is provided, returns an error.
If both are provided, text takes priority."""

    def execute(self, params, workdir=None):
        import os

        text = params.get("text")
        path = params.get("path")
        model = params.get("model", "cl100k_base")

        if not text and not path:
            return {"error": "Provide 'text' or 'path' parameter."}

        if not text:
            if workdir and not os.path.isabs(path):
                path = os.path.join(workdir, path)
            if not os.path.isfile(path):
                return {"error": f"File not found: {path}"}
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except Exception as e:
                return {"error": f"Failed to read file: {e}"}

        chars = len(text)
        words = len(text.split())
        lines = text.count("\n") + 1

        result = {
            "characters": chars,
            "words": words,
            "lines": lines,
            "tokens_chars_div_4": chars // 4,
            "tokens_words_times_1.3": int(words * 1.3),
        }

        try:
            import tiktoken
            enc = tiktoken.get_encoding(model)
            result["tokens_tiktoken"] = len(enc.encode(text))
            result["tiktoken_encoding"] = model
        except ImportError:
            result["tokens_tiktoken"] = "tiktoken not installed (pip install tiktoken)"
        except Exception as e:
            result["tokens_tiktoken"] = f"tiktoken error: {e}"

        return result
