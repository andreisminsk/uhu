"""Subprocess management helpers."""

from .platform import terminal


def kill_proc_tree(proc):
    """Kill a process and its entire process group."""
    terminal.kill_process_tree(proc)
