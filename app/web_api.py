"""Local HTTP API for the Svelte workspace."""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.providers_setup import configure
from hybrid_rag.config import settings
from hybrid_rag.core.base import DocStatus
from hybrid_rag.core.utils import validate_workspace
from hybrid_rag.ingestion import workspace_pool as ingestion_pool
from hybrid_rag.retrieval.workspace import workspace_pool as retrieval_pool

ROOT = Path(__file__).resolve().parent.parent
ORIGINALS_DIR = ROOT / "data" / "originals"
MAX_UPLOAD_BYTES = 250 * 1024 * 1024
SUPPORTED_EXTENSIONS = {".md", ".markdown", ".txt", ".pdf", ".docx", ".pptx", ".doc", ".ppt"}

JobStatus = Literal["queued", "processing", "completed", "failed"]
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = asyncio.Lock()


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


async def _publish_job_event(job_id: str, payload: dict[str, Any]) -> None:
    job = _jobs.get(job_id)
    if job is None:
        return
    condition: asyncio.Condition = job["condition"]
    async with condition:
        event = {"sequence": len(job["events"]) + 1, **payload}
        job["events"].append(event)
        condition.notify_all()


async def _job_event_stream(job: dict[str, Any]):
    cursor = 0
    condition: asyncio.Condition = job["condition"]
    while True:
        async with condition:
            try:
                await asyncio.wait_for(
                    condition.wait_for(
                        lambda: cursor < len(job["events"])
                        or job["status"] in {"completed", "failed"}
                    ),
                    timeout=15,
                )
            except TimeoutError:
                pass
            events = job["events"][cursor:]
            cursor += len(events)
            terminal = job["status"] in {"completed", "failed"} and cursor >= len(job["events"])
        if not events:
            if terminal:
                break
            yield ": keep-alive\n\n"
            continue
        for event in events:
            yield _sse(event)
        if terminal:
            break


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    workspace: str = "docs"


class ChatResponse(BaseModel):
    question: str
    answer: str
    refused: bool
    sources: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    relationships: list[dict[str, Any]]


class DocumentSummary(BaseModel):
    doc_id: str
    file_name: str
    status: str
    message: str | None = None


class DocumentsResponse(BaseModel):
    workspace: str
    documents: list[DocumentSummary]


class IngestionAccepted(BaseModel):
    job_id: str
    filename: str
    status: JobStatus


class IngestionJob(BaseModel):
    job_id: str
    filename: str
    status: JobStatus
    result: dict[str, Any] | None = None
    error: str | None = None


class GraphResponse(BaseModel):
    workspace: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    truncated: bool


def _workspace(value: str | None) -> str:
    name = (value or os.getenv("WORKSPACE", "docs")).strip()
    try:
        return validate_workspace(name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _upload_name(value: str | None) -> str:
    name = (value or "upload").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip(" .")
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=422, detail="Nama file tidak valid.")
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(status_code=415, detail=f"Format tidak didukung. Gunakan: {supported}")
    return name


async def _save_upload(upload: UploadFile) -> tuple[Path, str]:
    filename = _upload_name(upload.filename)
    ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix
    stem = Path(filename).stem

    for attempt in range(4):
        unique_name = filename if attempt == 0 else f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"
        path = ORIGINALS_DIR / unique_name
        try:
            output = path.open("xb")
        except FileExistsError:
            continue
        break
    else:
        raise HTTPException(status_code=409, detail="Tidak dapat membuat nama file unik.")

    total = 0
    try:
        with output:
            while chunk := await upload.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Ukuran file melebihi batas 250 MiB.")
                output.write(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    if total == 0:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="File kosong.")
    return path, path.name


async def _run_ingestion(job_id: str, path: Path, workspace: str, force: bool) -> None:
    async with _jobs_lock:
        job = _jobs[job_id]
        job["status"] = "processing"
    await _publish_job_event(
        job_id, {"event": "status", "status": "processing", "message": "Pipeline ingest dimulai."}
    )
    try:
        from app.commands.ingest import _ingest_one
        from app.providers_setup import capture_progress_events

        loop = asyncio.get_running_loop()

        def sink(payload: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(
                lambda: asyncio.create_task(
                    _publish_job_event(job_id, {"event": "progress", **payload})
                )
            )

        with capture_progress_events(sink):
            result = await _ingest_one(path, workspace, force=force)
        successful = result.get("status") in {"ok", "skip"}
        state = "completed" if successful else "failed"
        async with _jobs_lock:
            job.update(status=state, result=result, error=None if successful else result.get("message"))
        await _publish_job_event(
            job_id,
            {
                "event": "status",
                "status": state,
                "message": result.get("message") or ("Ingest selesai." if successful else "Ingest gagal."),
                "result": result,
            },
        )
    except Exception as exc:
        async with _jobs_lock:
            job.update(status="failed", error=str(exc))
        await _publish_job_event(job_id, {"event": "status", "status": "failed", "message": str(exc)})

@asynccontextmanager
async def lifespan(_: FastAPI):
    configure()
    yield
    await ingestion_pool.shutdown()
    await retrieval_pool.shutdown()
    from hybrid_rag.storage.neo4j_driver import close_neo4j_driver

    await close_neo4j_driver()


app = FastAPI(
    title="BasisData-RAG API",
    description="API lokal untuk ingest dokumen, tanya-jawab bersitasi, dan knowledge graph.",
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


@app.get("/api/health", tags=["system"])
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/documents", response_model=DocumentsResponse, tags=["documents"])
async def list_documents(workspace: str | None = Query(default=None)) -> DocumentsResponse:
    ws = _workspace(workspace)
    async with ingestion_pool.lease(ws) as rag:
        documents = await rag.doc_status.get_docs_by_statuses(
            [DocStatus.PROCESSED, DocStatus.PROCESSING, DocStatus.FAILED, DocStatus.PENDING]
        )

    entries = documents.items() if isinstance(documents, dict) else []
    result: list[DocumentSummary] = []
    for key, doc in entries:
        get = doc.get if isinstance(doc, dict) else (lambda name, item=doc: getattr(item, name, None))
        doc_id = str(get("id") or get("doc_id") or key or "")
        result.append(
            DocumentSummary(
                doc_id=doc_id,
                file_name=str(get("file_path") or get("doc_name") or doc_id),
                status=str(get("status") or "unknown"),
                message=get("error_msg") or get("message"),
            )
        )
    result.sort(key=lambda item: (item.file_name.casefold(), item.doc_id))
    return DocumentsResponse(workspace=ws, documents=result)


@app.post("/api/ingestions", response_model=IngestionAccepted, status_code=202, tags=["ingestion"])
async def start_ingestion(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    workspace: str | None = Query(default=None),
    force: bool = Query(default=False),
) -> IngestionAccepted:
    ws = _workspace(workspace)
    path, filename = await _save_upload(file)
    job_id = uuid.uuid4().hex
    condition = asyncio.Condition()
    async with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "filename": filename,
            "status": "queued",
            "result": None,
            "error": None,
            "events": [],
            "condition": condition,
        }
    await _publish_job_event(
        job_id,
        {"event": "status", "status": "queued", "message": "File diterima, menunggu ingest."},
    )
    background_tasks.add_task(_run_ingestion, job_id, path, ws, force)
    return IngestionAccepted(job_id=job_id, filename=filename, status="queued")


@app.get("/api/ingestions/{job_id}", response_model=IngestionJob, tags=["ingestion"])
async def ingestion_status(job_id: str) -> IngestionJob:
    async with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job ingest tidak ditemukan.")
        return IngestionJob(**job)


@app.get(
    "/api/ingestions/{job_id}/events",
    tags=["ingestion"],
    response_class=StreamingResponse,
    description="SSE JSON berisi status antrean dan event stage, skip, activity, lalu status akhir ingest.",
)
async def ingestion_events(job_id: str) -> StreamingResponse:
    async with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job ingest tidak ditemukan.")
    return StreamingResponse(
        _job_event_stream(job),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _chat_response(result: Any) -> ChatResponse:
    return ChatResponse(
        question=result.question,
        answer=result.text,
        refused=result.refused,
        sources=result.sources,
        entities=result.entities,
        relationships=result.relationships,
    )


@app.post("/api/chat", response_model=ChatResponse, tags=["chat"])
async def chat(request: ChatRequest) -> ChatResponse:
    ws = _workspace(request.workspace)
    try:
        from app.answer import answer_question

        result = await answer_question(request.question, workspace=ws)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gagal menjalankan tanya-jawab: {exc}") from exc
    return _chat_response(result)


@app.post(
    "/api/chat/stream",
    tags=["chat"],
    response_class=StreamingResponse,
    description="SSE JSON berisi tahap retrieve, rerank, generate, verifikasi sitasi, dan hasil akhir.",
)
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    ws = _workspace(request.workspace)
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def progress(event: dict[str, Any]) -> None:
        queue.put_nowait({"event": "progress", **event})

    async def run() -> None:
        try:
            from app.answer import answer_question
            from app.providers_setup import capture_progress_events

            def log_progress(event: dict[str, Any]) -> None:
                queue.put_nowait(
                    {
                        "event": "progress",
                        "kind": event.get("event", "activity"),
                        "message": event.get("message", ""),
                        **{key: value for key, value in event.items() if key not in {"event", "message"}},
                    }
                )

            with capture_progress_events(log_progress):
                result = await answer_question(request.question, workspace=ws, progress=progress)
            queue.put_nowait({"event": "complete", "data": _chat_response(result).model_dump()})
        except Exception as exc:
            queue.put_nowait({"event": "error", "message": str(exc)})
    async def stream():
        task = asyncio.create_task(run())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield _sse(event)
                if event["event"] in {"complete", "error"}:
                    break
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _read_graph_data(
    workspace: str,
    limit: int,
    notify: Callable[[dict[str, Any]], None] | None = None,
) -> GraphResponse:
    def report(stage: str, message: str, **details: Any) -> None:
        if notify is not None:
            notify({"stage": stage, "message": message, **details})

    if not settings.neo4j_uri:
        report("disabled", "Neo4j tidak aktif; graph kosong.")
        return GraphResponse(workspace=workspace, nodes=[], edges=[], truncated=False)

    try:
        report("connecting", "Membuka koneksi ke Neo4j.")
        async with retrieval_pool.lease(workspace) as rag:
            graph = rag.chunk_entity_relation_graph
            report("reading_nodes", "Membaca entitas.")
            raw_nodes = await graph.get_all_nodes()
            report("reading_edges", "Membaca relasi.")
            raw_edges = await graph.get_all_edges()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Gagal membaca knowledge graph: {exc}") from exc

    raw_nodes.sort(key=lambda node: str(node.get("entity_name") or node.get("id") or "").casefold())
    selected = raw_nodes[:limit]
    ids = {str(node.get("id") or node.get("entity_id")) for node in selected}
    nodes = [
        {
            "id": str(node.get("id") or node.get("entity_id")),
            "label": str(node.get("entity_name") or node.get("name") or node.get("id") or "Entitas"),
            "type": str(node.get("entity_type") or node.get("type") or "Entitas"),
            "description": str(node.get("description") or ""),
        }
        for node in selected
        if node.get("id") or node.get("entity_id")
    ]
    edge_candidates = [
        edge
        for edge in raw_edges
        if str(edge.get("source")) in ids and str(edge.get("target")) in ids
    ]
    selected_edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    for edge in edge_candidates:
        source, target = str(edge["source"]), str(edge["target"])
        label = str(edge.get("keywords") or edge.get("relation_type") or edge.get("label") or "terkait")
        key = (*sorted((source, target)), label)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        selected_edges.append(edge)
    edges = [
        {
            "source": str(edge["source"]),
            "target": str(edge["target"]),
            "label": str(edge.get("keywords") or edge.get("relation_type") or edge.get("label") or "terkait"),
            "description": str(edge.get("description") or ""),
        }
        for edge in selected_edges[: limit * 3]
    ]
    response = GraphResponse(
        workspace=workspace,
        nodes=nodes,
        edges=edges,
        truncated=len(raw_nodes) > len(selected) or len(selected_edges) > len(edges),
    )
    report("complete", "Graph siap.", nodes=len(nodes), edges=len(edges))
    return response


@app.get("/api/graph", response_model=GraphResponse, tags=["knowledge graph"])
async def knowledge_graph(
    workspace: str | None = Query(default=None),
    limit: int = Query(default=250, ge=1, le=1000),
) -> GraphResponse:
    return await _read_graph_data(_workspace(workspace), limit)


@app.get(
    "/api/graph/stream",
    tags=["knowledge graph"],
    response_class=StreamingResponse,
    description="SSE JSON berisi tahap koneksi Neo4j, pembacaan node/relasi, dan GraphResponse akhir.",
)
async def graph_stream(
    workspace: str | None = Query(default=None),
    limit: int = Query(default=80, ge=1, le=1000),
) -> StreamingResponse:
    ws = _workspace(workspace)
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def run() -> None:
        try:
            result = await _read_graph_data(
                ws,
                limit,
                notify=lambda event: queue.put_nowait({"event": "progress", **event}),
            )
            queue.put_nowait({"event": "complete", "data": result.model_dump()})
        except Exception as exc:
            queue.put_nowait({"event": "error", "message": str(exc)})

    async def stream():
        task = asyncio.create_task(run())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield _sse(event)
                if event["event"] in {"complete", "error"}:
                    break
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
