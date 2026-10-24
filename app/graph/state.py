"""State graf `ask` (SYSTEM_ANALYSIS bagian 16)."""

from __future__ import annotations

from typing import TypedDict


class AskState(TypedDict, total=False):
    # masukan
    question: str
    workspace: str | None
    return_parent: bool
    max_retries: int
    min_score: float | None

    # retrieve
    context: str
    chunks: list[dict]
    sources: list[dict]
    sources_block: str
    image_paths: list[str]

    # generate / verify
    answer: str
    problems: list[str]
    refused: bool
    attempts: int
    llm_calls: int
