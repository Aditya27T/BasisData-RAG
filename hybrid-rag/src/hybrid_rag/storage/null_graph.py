"""Graph storage no-op: dipakai saat ``NEO4J_URI`` kosong (graf mati).

Menggantikan :class:`hybrid_rag.storage.neo4j.Neo4JStorage` supaya
ingestion, retrieval, dan deletion berjalan penuh tanpa Neo4j — sesuai PRD
(F6/F11): flag graf mati berarti Neo4j tidak diperlukan dan tidak dijalankan,
tanpa menyentuh alur lain. Ekstraksi entitas/relasi lewat LLM ikut dilewati
oleh gate di ``ingestion/worker.py``.

Semua metode bertanda ``_skip_*``: writes menjadi no-op, reads kembalikan
struktur kosong sehingga kode pemanggil tidak butuh cabang khusus.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from hybrid_rag.config import settings
from hybrid_rag.core.base import BaseGraphStorage
from hybrid_rag.core.types import KnowledgeGraph
from hybrid_rag.core.utils import EmbeddingFunc

logger = logging.getLogger(__name__)


@dataclass
class NullGraphStorage(BaseGraphStorage):
    """Semua operasi graf berperilaku seperti graf kosong."""

    def _warn_once(self, method: str) -> None:
        logger.debug("NullGraphStorage: %s dilewati (graf mati)", method)

    # ── Reads: selalu "tidak ada" ───────────────────────────────────────────

    async def has_node(self, node_id: str) -> bool:
        return False

    async def has_edge(self, source_node_id: str, target_node_id: str) -> bool:
        return False

    async def get_node(self, node_id: str) -> dict[str, str] | None:
        return None

    async def get_edge(
        self, source_node_id: str, target_node_id: str
    ) -> dict[str, str] | None:
        return None

    async def get_node_edges(self, source_node_id: str) -> list[tuple[str, str]] | None:
        return None

    async def get_nodes_batch(self, node_ids: list[str]) -> dict[str, dict]:
        self._warn_once("get_nodes_batch")
        return {}

    async def node_degrees_batch(self, node_ids: list[str]) -> dict[str, int]:
        return {node_id: 0 for node_id in node_ids}

    async def edge_degrees_batch(
        self, edge_pairs: list[tuple[str, str]]
    ) -> dict[tuple[str, str], int]:
        return {pair: 0 for pair in edge_pairs}

    async def get_edges_batch(
        self, pairs: list[dict[str, str]]
    ) -> dict[tuple[str, str], dict]:
        self._warn_once("get_edges_batch")
        return {}

    async def get_nodes_edges_batch(
        self, node_ids: list[str]
    ) -> dict[str, list[tuple[str, str]]]:
        self._warn_once("get_nodes_edges_batch")
        return {node_id: [] for node_id in node_ids}

    # ── Writes: no-op ────────────────────────────────────────────────────────

    async def upsert_node(self, node_id: str, node_data: dict[str, str]) -> None:
        self._warn_once("upsert_node")

    async def upsert_nodes_batch(
        self, nodes: list[tuple[str, dict[str, str]]]
    ) -> None:
        self._warn_once("upsert_nodes_batch")

    async def upsert_edges_batch(
        self, edges: list[tuple[str, str, dict[str, str]]]
    ) -> None:
        self._warn_once("upsert_edges_batch")

    async def upsert_edge(
        self, source_node_id: str, target_node_id: str, edge_data: dict[str, str]
    ) -> None:
        self._warn_once("upsert_edge")

    async def remove_nodes(self, nodes: list[str]) -> None:
        self._warn_once("remove_nodes")

    async def remove_edges(self, edges: list[tuple[str, str]]) -> None:
        self._warn_once("remove_edges")

    # ── Blok global ──────────────────────────────────────────────────────────

    async def get_knowledge_graph(
        self,
        node_label: str,
        max_depth: int = 3,
        max_nodes: int = 1000,
        workspace: str | None = None,
    ) -> KnowledgeGraph:
        self._warn_once("get_knowledge_graph")
        return KnowledgeGraph(nodes=[], edges=[], is_truncated=False)

    async def get_all_nodes(self) -> list[dict]:
        self._warn_once("get_all_nodes")
        return []

    async def get_all_edges(self) -> list[dict]:
        self._warn_once("get_all_edges")
        return []

    async def get_popular_labels(self, limit: int = 300) -> list[str]:
        self._warn_once("get_popular_labels")
        return []

    async def search_labels(self, query: str, limit: int = 50) -> list[str]:
        self._warn_once("search_labels")
        return []

    async def index_done_callback(self) -> None:
        pass


def graph_enabled() -> bool:
    """Graf hidup hanya bila ``NEO4J_URI`` diset."""
    return bool(settings.neo4j_uri)


def create_graph_storage(
    *,
    namespace: Any,
    workspace: str,
    embedding_func: EmbeddingFunc | None,
    global_config: dict[str, Any] | None,
) -> BaseGraphStorage:
    """Kembalikan Neo4JStorage bila graf hidup, NullGraphStorage bila mati.

    Tanda tangan cocok dengan pola
    ``partial(Neo4JStorage, global_config=...)(namespace=..., workspace=..., embedding_func=...)``
    yang dipakai ``ingestion/rag.py`` dan ``retrieval/rag.py``.
    """
    if graph_enabled():
        from hybrid_rag.storage.neo4j import Neo4JStorage

        return Neo4JStorage(
            namespace=namespace,
            workspace=workspace,
            embedding_func=embedding_func,
            global_config=global_config or {},
        )
    return NullGraphStorage(
        namespace=namespace,
        workspace=workspace,
        embedding_func=embedding_func,
        global_config=global_config or {},
    )
