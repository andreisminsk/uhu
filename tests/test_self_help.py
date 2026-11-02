"""Tests for the self-help system-prompt section (questions about uhu itself)."""

import os

from ollama_agent.system_prompt import build_self_help_section, build_system_prompt


def test_section_points_to_local_manual():
    # Running from the repo → package parent dir contains README.md
    section = build_self_help_section()
    assert "SELF-HELP" in section
    assert "README.md" in section


def test_section_instructs_read_first():
    section = build_self_help_section()
    assert "FILE:" in section
    assert "read_file" in section


def test_section_defaults_to_workdir():
    # "this app" is ambiguous — default assumption is the workdir project,
    # with a hint letting the user switch to uhu's manual later.
    section = build_self_help_section()
    assert "DEFAULT TO WORKDIR" in section
    assert "assume the user means the workdir project" in section
    assert "hint" in section


def test_system_prompt_contains_self_help_with_agent():
    prompt = build_system_prompt(os.getcwd(), agent=True, tools=False, skills=False)
    assert "SELF-HELP" in prompt


def test_self_help_absent_without_file_access():
    prompt = build_system_prompt(os.getcwd(), agent=False, tools=False, skills=False)
    assert "SELF-HELP" not in prompt
