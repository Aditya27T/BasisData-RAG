"""Konfigurasi hybrid_rag.providers untuk aplikasi ini.

Dipanggil SEKALI di awal tiap proses CLI sebelum instance apa pun dibangun.
Menyuntikkan:
  - get_llm       → ChatOpenAI for OpenAI-compatible models; Google GenAI Interactions for Gemini VLM
  - get_embeddings → langchain_openai.OpenAIEmbeddings (kompatibel OpenAI)
  - rerank        → FastEmbed multilingual cross-encoder when RERANK_MODEL is set
  - s3            → _NoOpS3 (tidak pakai Textract/S3 di project ini)
  - progress      → _CliProgress (cetak stage ke stderr)

Semua nilai diambil dari settings hybrid_rag (yang baca dari .env),
sehingga satu .env mengkonfigurasi keduanya sekaligus.
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from functools import cache
from typing import Any, Callable

from hybrid_rag import providers
from hybrid_rag.config import settings

_progress_event_sink: ContextVar[Callable[[dict[str, Any]], None] | None] = ContextVar(
    "cobarag_progress_event_sink", default=None
)


@contextmanager
def capture_progress_events(sink: Callable[[dict[str, Any]], None]):
    token = _progress_event_sink.set(sink)
    try:
        yield
    finally:
        _progress_event_sink.reset(token)


class _GeminiInteractions:
    def __init__(self, model_id: str, api_key: str, timeout: float | int | None):
        from google import genai
        from google.genai import types

        http_options = types.HttpOptions(timeout=int(float(timeout) * 1000)) if timeout else None
        self._client = genai.Client(api_key=api_key, http_options=http_options)
        self._model_id = model_id
        self._timeout = float(timeout) if timeout is not None else None

    @staticmethod
    def _image_part(url: str) -> dict[str, str]:
        import mimetypes
        from urllib.parse import urlsplit

        if url.startswith("data:"):
            header, data = url.split(",", 1)
            mime_type = header[5:].split(";", 1)[0] or "image/jpeg"
            if ";base64" not in header:
                raise ValueError("Gemini VLM hanya menerima image data URI base64.")
            return {"type": "image", "data": data, "mime_type": mime_type}
        if url.startswith(("http://", "https://")):
            mime_type = mimetypes.guess_type(urlsplit(url).path)[0] or "image/jpeg"
            return {"type": "image", "uri": url, "mime_type": mime_type}
        raise ValueError("Sumber gambar VLM harus berupa data URI atau URL HTTP(S).")

    def _input(self, prompt_value: Any) -> tuple[str, list[dict[str, str]]]:
        if hasattr(prompt_value, "to_messages"):
            messages = prompt_value.to_messages()
        elif isinstance(prompt_value, (list, tuple)):
            messages = prompt_value
        else:
            messages = [{"type": "human", "content": str(prompt_value)}]
        system_text: list[str] = []
        input_parts: list[dict[str, str]] = []
        for message in messages:
            if isinstance(message, dict):
                role = message.get("type", "human")
                content = message.get("content", "")
            else:
                role = getattr(message, "type", "human")
                content = getattr(message, "content", "")
            if role == "system":
                if isinstance(content, str) and content:
                    system_text.append(content)
                continue
            blocks = content if isinstance(content, list) else [{"type": "text", "text": str(content)}]
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    input_parts.append({"type": "text", "text": str(block.get("text") or "")})
                elif block.get("type") in {"image_url", "image"}:
                    image_value = block.get("image_url", block)
                    image_url = image_value.get("url") if isinstance(image_value, dict) else image_value
                    if not isinstance(image_url, str) or not image_url:
                        raise ValueError("Blok gambar VLM tidak memiliki URL.")
                    input_parts.append(self._image_part(image_url))
        return "\n\n".join(system_text), input_parts

    def with_structured_output(self, schema: Any, method: str | None = None) -> Any:
        from langchain_core.runnables import RunnableLambda

        async def invoke(prompt_value: Any) -> Any:
            system_instruction, input_parts = self._input(prompt_value)
            if not input_parts:
                raise ValueError("Prompt VLM tidak berisi input.")
            response = await asyncio.to_thread(
                self._client.interactions.create,
                model=self._model_id,
                input=input_parts,
                system_instruction=system_instruction,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": schema.model_json_schema(),
                },
                generation_config={"temperature": 0.0},
                store=False,
                timeout=self._timeout,
            )
            output_text = getattr(response, "output_text", None)
            if not isinstance(output_text, str) or not output_text.strip():
                raise RuntimeError("Gemini Interactions tidak mengembalikan output JSON.")
            return schema.model_validate_json(output_text)

        return RunnableLambda(invoke)



# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------

def _get_llm(
    model_id: str,
    *,
    max_tokens: int | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float | int | None = None,
    temperature: float = 0.0,
) -> Any:
    """Create the configured chat client, or a direct Interactions client for Gemini VLM."""
    if model_id == settings.vlm_model and model_id.startswith("gemini-"):
        api_key = settings.vlm_binding_api_key
        if not api_key:
            raise RuntimeError("VLM_BINDING_API_KEY harus diisi untuk Gemini Interactions.")
        return _GeminiInteractions(model_id, api_key, timeout)
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:
        raise ImportError(
            "langchain-openai tidak terinstall. "
            "Jalankan: pip install langchain-openai"
        ) from e

    kwargs: dict[str, Any] = {
        "model": model_id,
        "temperature": temperature,
        "base_url": base_url,
        "api_key": api_key,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if timeout is not None:
        kwargs["timeout"] = float(timeout)

    return ChatOpenAI(**kwargs)


# ---------------------------------------------------------------------------
# Embedding factory
# ---------------------------------------------------------------------------

def _get_embeddings(
    model_id: str,
    base_url: str | None = None,
    api_key: str | None = None,
) -> Any:
    """Buat LangChain Embeddings melalui endpoint OpenAI-compatible.

    Default aplikasi adalah Ollama lokal di ``http://localhost:11434/v1``.
    Provider API tidak dijadikan fallback otomatis karena ingest dan query harus
    selalu memakai ruang vektor yang sama.
    """
    try:
        from langchain_openai import OpenAIEmbeddings
    except ImportError as e:
        raise ImportError(
            "langchain-openai tidak terinstall. "
            "Jalankan: pip install langchain-openai"
        ) from e

    return OpenAIEmbeddings(
        model=model_id,
        base_url=base_url,
        api_key=api_key,
        # Ollama menyediakan /v1/embeddings; pemeriksaan panjang konteks milik
        # OpenAI client tidak diperlukan untuk model lokal.
        check_embedding_ctx_length=False,
    )


@cache
def _reranker() -> Any:
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    return TextCrossEncoder(model_name=settings.rerank_model)


async def _rerank(
    query: str, documents: list[str], top_n: int | None = None
) -> list[dict[str, float | int]]:
    providers.progress.activity(f"Rerank lokal menilai {len(documents)} kandidat.")
    try:
        scores = await asyncio.to_thread(
            lambda: list(_reranker().rerank(query, documents))
        )
    except Exception:
        providers.progress.activity("Rerank lokal gagal; kandidat RRF tetap dipakai.")
        raise
    ranked = sorted(range(len(scores)), key=scores.__getitem__, reverse=True)
    if top_n is not None:
        ranked = ranked[:top_n]
    providers.progress.activity(f"Rerank selesai; dipilih {len(ranked)} kandidat.")
    return [
        {"index": index, "relevance_score": float(scores[index])}
        for index in ranked
    ]


# ---------------------------------------------------------------------------
# S3 no-op — project ini tidak pakai Textract/S3
# ---------------------------------------------------------------------------

class _NoOpS3:
    """Stub S3 untuk menghindari RuntimeError saat hook dipanggil.

    Parser yang dipakai (LlamaParse, md lokal) tidak butuh S3.
    Jika ada kode yang memanggil hook ini secara tak terduga, ia diam
    saja dan tidak crash — tapi log warning supaya bisa dideteksi.
    """

    def upload_figures_to_s3(self, *args: Any, **kwargs: Any) -> None:
        import logging
        logging.getLogger(__name__).warning(
            "upload_figures_to_s3 dipanggil tapi S3 tidak dikonfigurasi"
        )

    def upload_fileobj(self, *args: Any, **kwargs: Any) -> None:
        import logging
        logging.getLogger(__name__).warning(
            "upload_fileobj dipanggil tapi S3 tidak dikonfigurasi"
        )

    def delete_object(self, *args: Any, **kwargs: Any) -> None:
        pass

    def require_bucket(self, *args: Any, **kwargs: Any) -> None:
        pass


# ---------------------------------------------------------------------------
# Progress reporter — cetak stage ke stderr
# ---------------------------------------------------------------------------

class _CliProgress:
    """Cetak event progres ke stderr agar tidak campur dengan output stdout.

    Kontrak hook mengikuti `providers._Silent`: metode menerima
    ``*args, **kwargs`` supaya perubahan call-site package tidak memecah CLI.
    """

    current_doc_id: ContextVar[str | None] = ContextVar(
        "cobarag_doc_id", default=None
    )
    current_workspace: ContextVar[str | None] = ContextVar(
        "cobarag_workspace", default=None
    )

    def _publish(self, event: str, message: str, **details: Any) -> None:
        sink = _progress_event_sink.get()
        if sink is None:
            return
        payload = {"event": event, "message": message}
        doc_id = self.current_doc_id.get()
        workspace = self.current_workspace.get()
        if doc_id:
            payload["doc_id"] = doc_id
        if workspace:
            payload["workspace"] = workspace
        payload.update(details)
        sink(payload)

    def stage(self, *args: Any, **kwargs: Any) -> None:
        doc = self.current_doc_id.get()
        name = str(args[0]) if args else ""
        self._publish("stage", name, stage=name)
        label = f" [{doc}]" if doc else ""
        print(f"  ▸ {name}{label}", file=sys.stderr)

    def skip(self, *args: Any, **kwargs: Any) -> None:
        reason = " ".join(str(a) for a in args if a) or str(kwargs or "")
        self._publish("skip", reason)
        print(f"  ⏭ {reason}", file=sys.stderr)

    def activity(self, *args: Any, **kwargs: Any) -> None:
        message = str(args[0]) if args else ""
        self._publish("activity", message)
        print(f"  … {message}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_configured = False


def configure() -> None:
    """Panggil sekali sebelum memakai hybrid_rag.ingestion / retrieval."""
    global _configured
    if _configured:
        return

    providers.configure(
        get_llm=_get_llm,
        get_embeddings=_get_embeddings,
        rerank=_rerank,
        s3=_NoOpS3(),
        progress=_CliProgress(),
    )
    _configured = True
