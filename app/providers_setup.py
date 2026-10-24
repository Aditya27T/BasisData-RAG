"""Konfigurasi hybrid_rag.providers untuk aplikasi ini.

Dipanggil SEKALI di awal tiap proses CLI sebelum instance apa pun dibangun.
Menyuntikkan:
  - get_llm       → langchain_openai.ChatOpenAI (kompatibel OpenAI)
  - get_embeddings → langchain_openai.OpenAIEmbeddings (kompatibel OpenAI)
  - rerank        → None (dimatikan di v1)
  - s3            → _NoOpS3 (tidak pakai Textract/S3 di project ini)
  - progress      → _CliProgress (cetak stage ke stderr)

Semua nilai diambil dari settings hybrid_rag (yang baca dari .env),
sehingga satu .env mengkonfigurasi keduanya sekaligus.
"""

from __future__ import annotations

import sys
from typing import Any

from hybrid_rag import providers
from hybrid_rag.config import settings


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
    """Buat LangChain chat model yang kompatibel OpenAI."""
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
    """Buat LangChain Embeddings yang kompatibel OpenAI.

    Mendukung dua penyedia:
    - HuggingFace Inference API: base_url berakhiran nama model
    - OpenRouter atau endpoint lain: base_url adalah base API
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
        # HuggingFace Inference API memakai endpoint per model,
        # OpenAI-compat endpoint biasanya check_embedding_ctx_length perlu False
        check_embedding_ctx_length=False,
    )


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

from contextvars import ContextVar


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

    def stage(self, *args: Any, **kwargs: Any) -> None:
        doc = self.current_doc_id.get()
        label = f" [{doc}]" if doc else ""
        name = str(args[0]) if args else ""
        print(f"  ▸ {name}{label}", file=sys.stderr)

    def skip(self, *args: Any, **kwargs: Any) -> None:
        reason = " ".join(str(a) for a in args if a) or str(kwargs or "")
        print(f"  ⏭ {reason}", file=sys.stderr)

    def activity(self, *args: Any, **kwargs: Any) -> None:
        message = str(args[0]) if args else ""
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
        rerank=None,            # dimatikan di v1
        s3=_NoOpS3(),
        progress=_CliProgress(),
    )
    _configured = True
