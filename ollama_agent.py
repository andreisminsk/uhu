#!/usr/bin/env python3
"""
Interactive Ollama chat with conversation history and agentic coder mode.

This file is a thin wrapper around the ollama_agent package.
Usage: python ollama_agent.py [--host HOST] [--model MODEL] [--ctx CTX_SIZE] [--no-stream] [--log FILE] [--sessions-dir DIR] [--no-agent] [--workdir DIR]
"""

from ollama_agent.cli import main

if __name__ == "__main__":
    main()
