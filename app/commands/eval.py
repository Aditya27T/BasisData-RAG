"""CLI command for M3 baseline A/B evaluation."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from app.evaluation import (
    DEFAULT_QUESTIONS_PATH,
    DEFAULT_REPORTS_DIR,
    DatasetError,
    evaluate,
    load_dataset,
)


async def run(
    *,
    questions_path: Path = DEFAULT_QUESTIONS_PATH,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
    workspace: str | None = None,
    baselines: tuple[str, ...] = ("A", "B", "C"),
    max_retries: int = 0,
    use_judge: bool = True,
    validate_only: bool = False,
) -> None:
    """Validate the dataset, then run requested baselines and write reports."""
    try:
        dataset = load_dataset(questions_path)
    except DatasetError as exc:
        print(f"Dataset tidak valid: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    refusal_count = sum(case.expected_refusal for case in dataset.cases)
    print(f"Dataset   : {questions_path}")
    print(f"Pertanyaan: {len(dataset.cases)} ({refusal_count} penolakan)")
    if validate_only:
        print("Status    : valid")
        return

    from app.providers_setup import configure

    configure()
    selected = tuple(dict.fromkeys(baseline.upper() for baseline in baselines))
    print(f"Baseline  : {', '.join(selected)}")
    print(f"LLM judge : {'aktif' if use_judge else 'nonaktif'}")
    print("Menjalankan evaluasi secara serial...")

    try:
        result = await evaluate(
            dataset,
            workspace=workspace or os.getenv("WORKSPACE", "docs"),
            baselines=selected,
            reports_dir=reports_dir,
            max_retries=max(0, max_retries),
            use_judge=use_judge,
        )
    except (DatasetError, ValueError) as exc:
        print(f"Evaluasi gagal: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    print(f"JSON      : {result.json_path}")
    print(f"Markdown  : {result.markdown_path}")
    if result.error_count:
        print(f"Evaluasi selesai dengan {result.error_count} error kasus.", file=sys.stderr)
        raise SystemExit(1)
    print("Evaluasi selesai tanpa error kasus.")


def cmd_eval(
    *,
    questions_path: str,
    reports_dir: str,
    workspace: str | None,
    baselines: list[str] | None,
    max_retries: int,
    use_judge: bool,
    validate_only: bool,
) -> None:
    asyncio.run(
        run(
            questions_path=Path(questions_path).expanduser().resolve(),
            reports_dir=Path(reports_dir).expanduser().resolve(),
            workspace=workspace,
            baselines=tuple(baselines or ("A", "B", "C")),
            max_retries=max_retries,
            use_judge=use_judge,
            validate_only=validate_only,
        )
    )
