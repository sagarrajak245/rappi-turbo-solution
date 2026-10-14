"""Prompt texts live next to this file as Markdown so they read (and diff) like documents."""

from functools import cache
from pathlib import Path


@cache
def load_prompt(name: str) -> str:
    return (Path(__file__).parent / f"{name}.md").read_text(encoding="utf-8")
