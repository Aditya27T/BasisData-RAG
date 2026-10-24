"""Orkestrasi `ask` dengan LangGraph (PRD v0.3 F14).

Graf hanya menyambungkan fungsi biasa di `app.answer`; tidak ada logika baru di
dalam simpul. Tanpa checkpointer dan tanpa memori percakapan (SYSTEM_ANALYSIS
bagian 16, aturan 3).
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.answer import (
    REFUSAL,
    Answer,
    generate_answer,
    is_context_sufficient,
    is_refusal,
    max_retries_default,
    min_score_default,
    retrieve,
    verify_citations,
)
from app.graph.state import AskState


async def _retrieve_node(state: AskState) -> dict:
    retrieved = await retrieve(
        state["question"],
        workspace=state.get("workspace"),
        return_parent=bool(state.get("return_parent")),
    )
    return {
        "context": retrieved.context,
        "chunks": retrieved.chunks,
        "sources": retrieved.sources,
        "sources_block": retrieved.sources_block,
        "image_paths": retrieved.image_paths,
    }


def _decide_node(state: AskState) -> dict:
    sufficient = is_context_sufficient(
        list(state.get("chunks") or []), state.get("min_score")
    )
    return {"refused": not sufficient}


async def _generate_node_async(state: AskState) -> dict:
    answer = await generate_answer(
        state["question"], state.get("context", ""), state.get("sources_block", "")
    )
    return {
        "answer": answer.strip(),
        "attempts": int(state.get("attempts", 0)) + 1,
        "llm_calls": int(state.get("llm_calls", 0)) + 1,
    }


def _verify_node(state: AskState) -> dict:
    answer = state.get("answer", "")
    problems = verify_citations(answer, list(state.get("sources") or []))
    return {"problems": problems, "refused": is_refusal(answer)}


def _refuse_node(state: AskState) -> dict:
    return {"answer": REFUSAL, "refused": True}


def _route_after_decide(state: AskState) -> str:
    return "refuse" if state.get("refused") else "generate"


def _route_after_verify(state: AskState) -> str:
    if not state.get("problems"):
        return "end"

    allowed_attempts = int(state.get("max_retries", 0)) + 1
    if int(state.get("attempts", 0)) < allowed_attempts:
        return "generate"
    return "refuse"


def _build_graph():
    graph = StateGraph(AskState)
    graph.add_node("retrieve", _retrieve_node)
    graph.add_node("decide", _decide_node)
    graph.add_node("generate", _generate_node_async)
    graph.add_node("verify", _verify_node)
    graph.add_node("refuse", _refuse_node)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "decide")
    graph.add_conditional_edges(
        "decide", _route_after_decide, {"refuse": "refuse", "generate": "generate"}
    )
    graph.add_edge("generate", "verify")
    graph.add_conditional_edges(
        "verify", _route_after_verify, {"end": END, "generate": "generate", "refuse": "refuse"}
    )
    graph.add_edge("refuse", END)
    return graph.compile()


_GRAPH = _build_graph()


async def ask_graph(
    question: str,
    workspace: str | None = None,
    return_parent: bool = False,
    max_retries: int | None = None,
    min_score: float | None = None,
) -> Answer:
    """Jalankan graf dan kembalikan kontrak `Answer` yang sama dengan `ask()`."""
    if max_retries is None:
        max_retries = max_retries_default()
    if min_score is None:
        min_score = min_score_default()

    final = await _GRAPH.ainvoke(
        {
            "question": question,
            "workspace": workspace,
            "return_parent": return_parent,
            "max_retries": max_retries,
            "min_score": min_score,
            "attempts": 0,
            "llm_calls": 0,
        },
        {"recursion_limit": 2 * (max_retries + 1) + 6},
    )

    return Answer(
        question=question,
        text=final.get("answer", REFUSAL),
        refused=bool(final.get("refused")),
        sources=list(final.get("sources") or []),
        sources_block=final.get("sources_block", ""),
        chunks=list(final.get("chunks") or []),
        problems=list(final.get("problems") or []),
        attempts=int(final.get("attempts", 0)),
        llm_calls=int(final.get("llm_calls", 0)),
        image_paths=list(final.get("image_paths") or []),
    )
