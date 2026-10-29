"""M3 evaluation runner for full-corpus and hybrid-retrieval baselines."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from app.answer import (
    Answer,
    build_refusal,
    citations_in,
    generate_answer,
    is_refusal,
    verify_citations,
)
from app.citations import headings_in, render_sources

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QUESTIONS_PATH = PROJECT_ROOT / "eval" / "questions.yaml"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "eval" / "reports"
ORIGINALS_DIR = PROJECT_ROOT / "data" / "originals"
PARSED_DIR = PROJECT_ROOT / "data" / "parsed"

_TEXT_EXTENSIONS = {".md", ".markdown", ".txt"}
_PARSED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".doc", ".ppt"}
_PAGE_RE = re.compile(r"hal\.?\s*(\d+)", re.IGNORECASE)
_JUDGE_PROMPT = """\
Nilai jawaban kandidat hanya terhadap pertanyaan, jawaban acuan, dan bukti dokumen.
Kembalikan tepat satu objek JSON tanpa markdown:
{{"answer_correct": true|false, "faithful": true|false, "reason": "alasan singkat"}}

answer_correct bernilai true bila jawaban kandidat menyampaikan fakta utama jawaban acuan.
faithful bernilai true bila setiap klaim faktual kandidat didukung bukti dokumen.
Jangan memakai pengetahuan di luar bukti dokumen.

Pertanyaan:
{question}

Jawaban acuan:
{reference}

Bukti dokumen:
{context}

Jawaban kandidat:
{candidate}
"""


class DatasetError(ValueError):
    """Dataset evaluasi tidak memenuhi kontrak M3."""


@dataclass(frozen=True)
class ExpectedCitation:
    file: str
    page: int | None = None
    heading: str | None = None


@dataclass(frozen=True)
class EvalCase:
    id: str
    question: str
    expected_refusal: bool
    reference_answer: str | None
    citations: tuple[ExpectedCitation, ...]
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvalDataset:
    cases: tuple[EvalCase, ...]
    owner_authored: bool


@dataclass(frozen=True)
class FullCorpus:
    context: str
    sources: tuple[dict[str, Any], ...]
    sources_block: str
    document_count: int
    parsed_pages: int


@dataclass
class CaseResult:
    case_id: str
    baseline: str
    question: str
    expected_refusal: bool
    reference_answer: str | None
    answer: str = ""
    refused: bool = False
    refusal_correct: bool = False
    citation_correct: bool = False
    answer_correct: bool | None = None
    faithful: bool | None = None
    judge_reason: str | None = None
    citations: list[str] = field(default_factory=list)
    citation_problems: list[str] = field(default_factory=list)
    retrieved_chunks: int = 0
    graph_entities: int = 0
    graph_relationships: int = 0
    answer_llm_calls: int = 0
    judge_llm_calls: int = 0
    elapsed_ms: float = 0.0
    error: str | None = None


@dataclass(frozen=True)
class EvaluationRun:
    json_path: Path
    markdown_path: Path
    error_count: int


def load_dataset(path: Path, *, strict: bool = True) -> EvalDataset:
    """Load and validate the owner-authored M3 YAML dataset."""
    if not path.exists():
        raise DatasetError(
            f"Dataset tidak ditemukan: {path}. Buat 20-30 kasus owner-authored "
            "sesuai kontrak di docs/prd.md bagian 7."
        )

    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise DatasetError(f"Dataset tidak dapat dibaca: {exc}") from exc

    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise DatasetError("Dataset harus berupa objek YAML dengan version: 1")

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        raise DatasetError("metadata wajib berupa objek")
    owner_authored = metadata.get("owner_authored") is True
    if strict and not owner_authored:
        raise DatasetError("metadata.owner_authored harus true untuk set evaluasi resmi")

    raw_questions = payload.get("questions")
    if not isinstance(raw_questions, list):
        raise DatasetError("questions wajib berupa daftar")

    cases = tuple(_parse_case(item, index) for index, item in enumerate(raw_questions, 1))
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise DatasetError("Setiap question.id harus unik")

    refusal_count = sum(case.expected_refusal for case in cases)
    if strict and not 20 <= len(cases) <= 30:
        raise DatasetError(f"Set resmi harus berisi 20-30 kasus; ditemukan {len(cases)}")
    if strict and refusal_count < 5:
        raise DatasetError(f"Set resmi harus memuat minimal 5 penolakan; ditemukan {refusal_count}")

    return EvalDataset(cases=cases, owner_authored=owner_authored)


def _parse_case(raw: object, index: int) -> EvalCase:
    if not isinstance(raw, dict):
        raise DatasetError(f"questions[{index}] wajib berupa objek")

    case_id = _required_text(raw.get("id"), f"questions[{index}].id")
    question = _required_text(raw.get("question"), f"questions[{index}].question")
    expected = raw.get("expected")
    if not isinstance(expected, dict):
        raise DatasetError(f"questions[{index}].expected wajib berupa objek")

    refusal = expected.get("refusal")
    if not isinstance(refusal, bool):
        raise DatasetError(f"questions[{index}].expected.refusal wajib boolean")

    answer_raw = expected.get("answer")
    answer = answer_raw.strip() if isinstance(answer_raw, str) and answer_raw.strip() else None
    raw_citations = expected.get("citations", [])
    if not isinstance(raw_citations, list):
        raise DatasetError(f"questions[{index}].expected.citations wajib berupa daftar")
    citations = tuple(_parse_expected_citation(item, index) for item in raw_citations)

    if refusal and (answer is not None or citations):
        raise DatasetError(
            f"questions[{index}] adalah kasus penolakan; answer dan citations harus kosong"
        )
    if not refusal and (answer is None or not citations):
        raise DatasetError(
            f"questions[{index}] bukan penolakan; answer dan minimal satu citation wajib ada"
        )

    raw_tags = raw.get("tags", [])
    if not isinstance(raw_tags, list) or not all(
        isinstance(tag, str) and tag.strip() for tag in raw_tags
    ):
        raise DatasetError(f"questions[{index}].tags wajib berupa daftar string")

    return EvalCase(
        id=case_id,
        question=question,
        expected_refusal=refusal,
        reference_answer=answer,
        citations=citations,
        tags=tuple(tag.strip() for tag in raw_tags),
    )


def _parse_expected_citation(raw: object, case_index: int) -> ExpectedCitation:
    if not isinstance(raw, dict):
        raise DatasetError(
            f"questions[{case_index}].expected.citations[] wajib berupa objek"
        )
    file_name = _required_text(raw.get("file"), "citation.file")

    page = raw.get("page")
    if page is not None and (not isinstance(page, int) or isinstance(page, bool) or page < 1):
        raise DatasetError("citation.page harus bilangan bulat 1-based")

    heading_raw = raw.get("heading")
    heading = heading_raw.strip() if isinstance(heading_raw, str) and heading_raw.strip() else None
    return ExpectedCitation(file=file_name, page=page, heading=heading)


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DatasetError(f"{field_name} wajib berupa string non-kosong")
    return value.strip()


def load_full_corpus(
    originals_dir: Path = ORIGINALS_DIR,
    parsed_dir: Path = PARSED_DIR,
) -> FullCorpus:
    """Build baseline A context from originals and existing parse caches."""
    paths = sorted(
        path
        for path in originals_dir.iterdir()
        if path.is_file()
        and not path.name.startswith(".")
        and path.suffix.lower() in _TEXT_EXTENSIONS | _PARSED_EXTENSIONS
    )
    if not paths:
        raise DatasetError(f"Tidak ada dokumen sumber di {originals_dir}")

    sections: list[str] = []
    sources: list[dict[str, Any]] = []
    parsed_pages = 0

    for reference_id, path in enumerate(paths, 1):
        if path.suffix.lower() in _TEXT_EXTENSIONS:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if not text:
                continue
            headings = headings_in(text)
            sections.append(f"=== {path.name} ===\n{text}")
            sources.append(
                {
                    "reference_id": str(reference_id),
                    "file_path": path.name,
                    "headings": headings,
                    "page_label": None,
                    "page_first": None,
                    "page_last": None,
                    "chunk_id": None,
                }
            )
            continue

        digest = _sha256_file(path)
        cache_file = parsed_dir / f"{digest}.json"
        if not cache_file.exists():
            raise DatasetError(
                f"Cache parse untuk {path.name} tidak ditemukan. Jalankan ingest sebelum eval."
            )
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DatasetError(f"Cache parse {cache_file} rusak: {exc}") from exc

        content_list = payload.get("content_list")
        if not isinstance(content_list, list) or not content_list:
            raise DatasetError(f"Cache parse {cache_file} tidak memiliki content_list")

        pages: dict[int, list[str]] = {}
        for item in content_list:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            page_idx = item.get("page_idx", 0)
            try:
                page = max(1, int(page_idx) + 1)
            except (TypeError, ValueError):
                page = 1
            level = item.get("text_level")
            if isinstance(level, int) and 1 <= level <= 6:
                text = f"{'#' * level} {text}"
            pages.setdefault(page, []).append(text)

        for page, parts in sorted(pages.items()):
            text = "\n\n".join(parts)
            sections.append(f"=== {path.name}, hal. {page} ===\n{text}")
            sources.append(
                {
                    "reference_id": str(reference_id),
                    "file_path": path.name,
                    "headings": headings_in(text),
                    "page_label": f"hal. {page}",
                    "page_first": page,
                    "page_last": page,
                    "chunk_id": None,
                }
            )
            parsed_pages += 1

    if not sections:
        raise DatasetError("Dokumen sumber tidak menghasilkan konteks baseline A")

    return FullCorpus(
        context="\n\n".join(sections),
        sources=tuple(sources),
        sources_block=render_sources(list(sources)),
        document_count=len(paths),
        parsed_pages=parsed_pages,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


async def answer_full_corpus(case: EvalCase, corpus: FullCorpus, max_retries: int) -> Answer:
    """Run baseline A using every document as the answer context."""
    problems: list[str] = []
    attempts = 0
    for _ in range(max_retries + 1):
        text = await generate_answer(case.question, corpus.context, corpus.sources_block)
        attempts += 1
        problems = verify_citations(text, list(corpus.sources))
        if not problems:
            return Answer(
                question=case.question,
                text=text.strip(),
                refused=is_refusal(text),
                sources=list(corpus.sources),
                sources_block=corpus.sources_block,
                attempts=attempts,
                llm_calls=attempts,
            )

    return build_refusal(
        case.question,
        sources=list(corpus.sources),
        sources_block=corpus.sources_block,
        problems=problems,
        attempts=attempts,
        llm_calls=attempts,
    )


async def judge_answer(case: EvalCase, answer: Answer, context: str) -> dict[str, Any]:
    """Judge correctness and faithfulness in one explicitly counted LLM call."""
    if case.expected_refusal:
        correct = answer.refused
        return {
            "answer_correct": correct,
            "faithful": correct,
            "reason": "penolakan sesuai ground truth" if correct else "jawaban seharusnya ditolak",
            "calls": 0,
        }
    if answer.refused:
        return {
            "answer_correct": False,
            "faithful": False,
            "reason": "sistem menolak pertanyaan yang memiliki jawaban acuan",
            "calls": 0,
        }

    from hybrid_rag import providers
    from hybrid_rag.config import settings
    from langchain_core.messages import HumanMessage

    llm = providers.get_llm(
        model_id=settings.llm_model,
        max_tokens=256,
        base_url=settings.llm_binding_host,
        api_key=settings.llm_binding_api_key,
        temperature=0.0,
    )
    prompt = _JUDGE_PROMPT.format(
        question=case.question,
        reference=case.reference_answer,
        context=context,
        candidate=answer.text,
    )
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    content = response.content if isinstance(response.content, str) else str(response.content)
    payload = _parse_judge_json(content)
    return {**payload, "calls": 1}


def _parse_judge_json(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.IGNORECASE)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("judge tidak mengembalikan objek JSON")
    payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload.get("answer_correct"), bool):
        raise ValueError("judge.answer_correct bukan boolean")
    if not isinstance(payload.get("faithful"), bool):
        raise ValueError("judge.faithful bukan boolean")
    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("judge.reason kosong")
    return {
        "answer_correct": payload["answer_correct"],
        "faithful": payload["faithful"],
        "reason": reason.strip(),
    }


def citation_is_correct(case: EvalCase, answer: Answer) -> bool:
    """Check that a valid output citation matches one acceptable ground-truth source."""
    if case.expected_refusal:
        return answer.refused
    if answer.refused or answer.problems:
        return False
    return any(
        _citation_matches(actual, expected)
        for actual in citations_in(answer.text)
        for expected in case.citations
    )


def _citation_matches(actual: str, expected: ExpectedCitation) -> bool:
    parts = [part.strip().strip("\"'") for part in actual.split(",", 1)]
    actual_file = parts[0].replace("\\", "/").rsplit("/", 1)[-1]
    expected_file = expected.file.replace("\\", "/").rsplit("/", 1)[-1]
    if actual_file.casefold() != expected_file.casefold():
        return False
    if expected.page is None and expected.heading is None:
        return True
    if len(parts) == 1:
        return False
    detail = parts[1]
    if expected.page is not None:
        match = _PAGE_RE.search(detail)
        return bool(match and int(match.group(1)) == expected.page)
    return bool(expected.heading and detail.casefold() == expected.heading.casefold())


def _answer_context(answer: Answer) -> str:
    return "\n\n".join(
        str(chunk.get("content") or "").strip()
        for chunk in answer.chunks
        if str(chunk.get("content") or "").strip()
    )


async def evaluate(
    dataset: EvalDataset,
    *,
    workspace: str,
    baselines: tuple[str, ...],
    reports_dir: Path,
    max_retries: int = 0,
    use_judge: bool = True,
    originals_dir: Path = ORIGINALS_DIR,
    parsed_dir: Path = PARSED_DIR,
) -> EvaluationRun:
    """Run requested baselines serially and write JSON plus Markdown reports."""
    invalid = [baseline for baseline in baselines if baseline not in {"A", "B", "C"}]
    if invalid or not baselines:
        raise ValueError(f"Baseline harus A, B, dan/atau C; diterima: {baselines}")

    corpus = load_full_corpus(originals_dir, parsed_dir) if "A" in baselines else None
    if "C" in baselines:
        from hybrid_rag.config import settings

        if not settings.neo4j_uri:
            raise DatasetError("Baseline C membutuhkan NEO4J_URI")
    results: list[CaseResult] = []

    for case in dataset.cases:
        for baseline in baselines:
            started = time.perf_counter()
            result = CaseResult(
                case_id=case.id,
                baseline=baseline,
                question=case.question,
                expected_refusal=case.expected_refusal,
                reference_answer=case.reference_answer,
            )
            try:
                if baseline == "A":
                    assert corpus is not None
                    answer = await answer_full_corpus(case, corpus, max_retries)
                    judge_context = corpus.context
                else:
                    from app.answer import answer_question

                    answer = await answer_question(
                        case.question,
                        workspace=workspace,
                        max_retries=max_retries,
                        include_graph=baseline == "C",
                    )
                    judge_context = _answer_context(answer)

                result.answer = answer.text
                result.refused = answer.refused
                result.refusal_correct = answer.refused == case.expected_refusal
                result.citation_correct = citation_is_correct(case, answer)
                result.citations = citations_in(answer.text)
                result.citation_problems = list(answer.problems)
                result.retrieved_chunks = len(answer.chunks)
                result.answer_llm_calls = answer.llm_calls
                result.graph_entities = len(answer.entities)
                result.graph_relationships = len(answer.relationships)

                if use_judge:
                    judged = await judge_answer(case, answer, judge_context)
                    result.answer_correct = judged["answer_correct"]
                    result.faithful = judged["faithful"]
                    result.judge_reason = judged["reason"]
                    result.judge_llm_calls = judged["calls"]
            except Exception as exc:
                result.error = f"{type(exc).__name__}: {exc}"
            finally:
                result.elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
                results.append(result)

    created_at = datetime.now(UTC)
    report = _build_report(dataset, baselines, results, corpus, created_at, use_judge)
    reports_dir.mkdir(parents=True, exist_ok=True)
    stem = created_at.strftime("eval-%Y%m%d-%H%M%S")
    json_path = reports_dir / f"{stem}.json"
    markdown_path = reports_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    return EvaluationRun(
        json_path=json_path,
        markdown_path=markdown_path,
        error_count=sum(result.error is not None for result in results),
    )


def _build_report(
    dataset: EvalDataset,
    baselines: tuple[str, ...],
    results: list[CaseResult],
    corpus: FullCorpus | None,
    created_at: datetime,
    use_judge: bool,
) -> dict[str, Any]:
    summaries = {
        baseline: _summarize([result for result in results if result.baseline == baseline])
        for baseline in baselines
    }
    comparison: dict[str, float | None] = {}
    if "A" in summaries and "B" in summaries:
        for metric in ("answer_accuracy", "citation_accuracy", "refusal_accuracy", "faithfulness"):
            left = summaries["A"][metric]
            right = summaries["B"][metric]
            comparison[f"B_minus_A_{metric}"] = (
                round(right - left, 4) if left is not None and right is not None else None
            )
    if "B" in summaries and "C" in summaries:
        for metric in ("answer_accuracy", "citation_accuracy", "refusal_accuracy", "faithfulness"):
            left = summaries["B"][metric]
            right = summaries["C"][metric]
            comparison[f"C_minus_B_{metric}"] = (
                round(right - left, 4) if left is not None and right is not None else None
            )

    return {
        "schema_version": 1,
        "created_at": created_at.isoformat(),
        "dataset": {
            "questions": len(dataset.cases),
            "refusal_questions": sum(case.expected_refusal for case in dataset.cases),
            "owner_authored": dataset.owner_authored,
        },
        "run": {
            "baselines": list(baselines),
            "judge_enabled": use_judge,
            "document_count": corpus.document_count if corpus else None,
            "parsed_pages": corpus.parsed_pages if corpus else None,
            "embedding_tokens": None,
            "embedding_tokens_note": "Engine belum mengekspos jumlah token embedding per query.",
        },
        "summaries": summaries,
        "comparison": comparison,
        "results": [asdict(result) for result in results],
    }


def _summarize(results: list[CaseResult]) -> dict[str, Any]:
    judged = [result for result in results if result.answer_correct is not None]
    faithful = [result for result in results if result.faithful is not None]
    return {
        "cases": len(results),
        "errors": sum(result.error is not None for result in results),
        "answer_accuracy": _ratio(result.answer_correct for result in judged),
        "citation_accuracy": _ratio(result.citation_correct for result in results),
        "refusal_accuracy": _ratio(result.refusal_correct for result in results),
        "faithfulness": _ratio(result.faithful for result in faithful),
        "answer_llm_calls": sum(result.answer_llm_calls for result in results),
        "judge_llm_calls": sum(result.judge_llm_calls for result in results),
        "graph_entities": sum(result.graph_entities for result in results),
        "graph_relationships": sum(result.graph_relationships for result in results),
        "average_latency_ms": round(
            sum(result.elapsed_ms for result in results) / len(results), 1
        )
        if results
        else None,
    }


def _ratio(values: Any) -> float | None:
    items = list(values)
    return round(sum(bool(value) for value in items) / len(items), 4) if items else None


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Laporan evaluasi M3/M4",
        "",
        f"Waktu UTC: `{report['created_at']}`",
        f"Jumlah pertanyaan: {report['dataset']['questions']}",
        f"Kasus penolakan: {report['dataset']['refusal_questions']}",
        f"LLM judge: {'aktif' if report['run']['judge_enabled'] else 'nonaktif'}",
        "",
        "## Ringkasan",
        "",
        "| Baseline | Jawaban benar | Sitasi benar | Penolakan benar | Faithfulness | "
        "Entitas | Relasi | Error | Panggilan LLM |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for baseline, summary in report["summaries"].items():
        total_calls = summary["answer_llm_calls"] + summary["judge_llm_calls"]
        lines.append(
            f"| {baseline} | {_percent(summary['answer_accuracy'])} | "
            f"{_percent(summary['citation_accuracy'])} | "
            f"{_percent(summary['refusal_accuracy'])} | "
            f"{_percent(summary['faithfulness'])} | {summary['graph_entities']} | "
            f"{summary['graph_relationships']} | {summary['errors']} | {total_calls} |"
        )

    if report["comparison"]:
        lines.extend(["", "## Selisih baseline", ""])
        for metric, delta in report["comparison"].items():
            lines.append(f"- `{metric}`: {_signed_percent(delta)}")

    lines.extend(
        [
            "",
            "## Hasil per pertanyaan",
            "",
            "| ID | Baseline | Refusal | Jawaban | Sitasi | Faithful | Error |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for result in report["results"]:
        lines.append(
            f"| {result['case_id']} | {result['baseline']} | "
            f"{_mark(result['refusal_correct'])} | {_mark(result['answer_correct'])} | "
            f"{_mark(result['citation_correct'])} | {_mark(result['faithful'])} | "
            f"{_escape_cell(result['error'] or '')} |"
        )

    lines.extend(
        [
            "",
            "## Batas pengukuran",
            "",
            f"- {report['run']['embedding_tokens_note']}",
            "- Correctness dan faithfulness bernilai `n/a` bila LLM judge dimatikan.",
            "- Baseline A memakai seluruh dokumen, baseline B memakai hybrid retrieval "
            "tanpa graf, dan baseline C menambahkan Neo4j.",
            "",
        ]
    )
    return "\n".join(lines)


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _signed_percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:+.1f} poin persentase"


def _mark(value: bool | None) -> str:
    if value is None:
        return "n/a"
    return "ya" if value else "tidak"


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
