"""Pengumpul metrik token embedding dari respons penyedia, bukan estimasi."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

SOURCE_PROVIDER_USAGE = "provider_usage"


@dataclass
class EmbeddingUsage:
    requests: int = 0
    usage_prompt_tokens: int = 0
    usage_total_tokens: int = 0
    usage_available: bool = False

    def note_request(self) -> None:
        self.requests += 1

    def record(self, prompt_tokens: int, total_tokens: int) -> None:
        self.usage_available = True
        self.usage_prompt_tokens += prompt_tokens
        self.usage_total_tokens += total_tokens


_current: ContextVar[EmbeddingUsage | None] = ContextVar(
    "basisdata_rag_embedding_usage", default=None
)


def start_capture() -> None:
    _current.set(EmbeddingUsage())


def note_request() -> None:
    usage = _current.get()
    if usage is not None:
        usage.note_request()


def record_usage(prompt_tokens: object, total_tokens: object = None) -> None:
    usage = _current.get()
    if usage is None:
        return
    try:
        prompt = int(prompt_tokens)
        total = int(total_tokens) if total_tokens is not None else prompt
    except (TypeError, ValueError):
        return
    if prompt < 0 or total < 0:
        return
    usage.record(prompt, total)


def take_capture() -> EmbeddingUsage | None:
    usage = _current.get()
    _current.set(None)
    return usage


def to_report_fields(
    usage: EmbeddingUsage | None,
) -> tuple[int | None, int, str | None]:
    requests = usage.requests if usage is not None else 0
    if usage is None or requests == 0 or not usage.usage_available:
        return None, requests, None
    return usage.usage_prompt_tokens, requests, SOURCE_PROVIDER_USAGE
