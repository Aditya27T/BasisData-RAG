"""Uji paritas `answer_question()` vs `ask_graph()` (SYSTEM_ANALYSIS bagian 16).

Keduanya harus menghasilkan keputusan refuse yang sama dan sitasi yang sama untuk
pertanyaan yang sama; selisih adalah bug, bukan variasi yang boleh diabaikan.

Pemakaian:
    python eval/parity.py
    python eval/parity.py --questions "Apa itu RRF?" "Siapa presiden?" --max-retries 0

Set eval resmi (eval/questions.yaml, M3) belum ada; daftar bawaan di bawah adalah
pertanyaan cepat atas dokumen uji. Ganti dengan set eval setelah M3 selesai.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_QUESTIONS = [
    "Apa itu RRF dan apa gunanya?",
    "Berapa nilai ambang evaluasi dan untuk apa dipakai?",
    "Siapa presiden pertama Amerika Serikat?",
]


async def _run_one(question: str, workspace: str, max_retries: int) -> tuple:
    from app.answer import answer_question, citations_in
    from app.graph.ask_graph import ask_graph

    plain = await answer_question(question, workspace=workspace, max_retries=max_retries)
    graph = await ask_graph(question, workspace=workspace, max_retries=max_retries)

    plain_cites = citations_in(plain.text)
    graph_cites = citations_in(graph.text)

    ok = plain.refused == graph.refused and plain_cites == graph_cites
    return ok, plain, graph, plain_cites, graph_cites


async def main() -> int:
    parser = argparse.ArgumentParser(description="Uji paritas ask() vs ask_graph()")
    parser.add_argument("--workspace", "-w", default=os.getenv("WORKSPACE", "docs"))
    parser.add_argument(
        "--max-retries",
        type=int,
        default=0,
        help="Batas retry verify (default 0 agar panggilan LLM = 2 per pertanyaan)",
    )
    parser.add_argument("--questions", nargs="*", default=None)
    args = parser.parse_args()

    from app.providers_setup import configure

    configure()

    questions = args.questions or DEFAULT_QUESTIONS
    failures = 0

    for question in questions:
        ok, plain, graph, plain_cites, graph_cites = await _run_one(
            question, args.workspace, args.max_retries
        )
        status = "OK  " if ok else "BEDA"
        print(f"[{status}] {question}")
        print(
            f"        plain: refused={plain.refused} llm_calls={plain.llm_calls} "
            f"sitasi={plain_cites}"
        )
        print(
            f"        graph: refused={graph.refused} llm_calls={graph.llm_calls} "
            f"sitasi={graph_cites}"
        )
        if not ok:
            failures += 1
            print(f"        plain text: {plain.text[:160]}")
            print(f"        graph text: {graph.text[:160]}")

    print()
    print(f"Hasil: {len(questions) - failures}/{len(questions)} paritas")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
