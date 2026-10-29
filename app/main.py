"""CLI entry point untuk cobarag.

Perintah yang tersedia:
  ingest          Masukkan file dari data/originals/ ke workspace
  ask             Tanya-jawab bersitasi berdasarkan dokumen
  list            Tampilkan semua dokumen di workspace
  delete          Hapus dokumen dari workspace
  eval            Bandingkan baseline seluruh dokumen dan hybrid retrieval
  probe-embedding Uji penyedia embedding dan simpan hasil ke docs/DECISIONS.md

Contoh pemakaian:
  python -m app.main probe-embedding
  python -m app.main ingest
  python -m app.main ingest data/originals/catatan.md
  python -m app.main ask "Apa itu RAG hybrid?"
  python -m app.main ask --graph "Apa itu RAG hybrid?"
  python -m app.main list
  python -m app.main delete doc-abc123...
  python -m app.main eval --validate-only

Atau via CLI entry point (setelah pip install -e .):
  cobarag probe-embedding
  cobarag ingest
  cobarag ask "Pertanyaan?"
  cobarag ask --graph "Pertanyaan?"
  cobarag list
  cobarag delete <doc_id>
  cobarag eval
"""

from __future__ import annotations

import argparse
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cobarag",
        description="RAG hybrid lokal dengan ParadeDB dan hybrid-rag.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--workspace", "-w",
        metavar="WORKSPACE",
        help="Nama workspace (default: env WORKSPACE atau 'docs')",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # ── probe-embedding ──
    sub.add_parser(
        "probe-embedding",
        help="Uji penyedia embedding dan simpan hasil ke docs/DECISIONS.md",
    )

    # ── ingest ──
    p_ingest = sub.add_parser(
        "ingest",
        help="Ingest file ke workspace (default: semua file di data/originals/)",
    )
    p_ingest.add_argument(
        "files",
        nargs="*",
        metavar="FILE",
        help="File yang akan di-ingest (opsional; default: semua di data/originals/)",
    )
    p_ingest.add_argument(
        "--force", "-f",
        action="store_true",
        help="Proses ulang meskipun sudah ter-ingest",
    )

    # ── ask ──
    p_ask = sub.add_parser(
        "ask",
        help="Tanya-jawab bersitasi berdasarkan dokumen di workspace",
    )
    p_ask.add_argument(
        "question",
        metavar="PERTANYAAN",
        help="Pertanyaan yang ingin dijawab",
    )
    p_ask.add_argument(
        "--parent", "-p",
        action="store_true",
        dest="return_parent",
        help="Kembalikan teks parent (lebih panjang) bukan child chunk",
    )
    p_ask.add_argument(
        "--graph", "-g",
        action="store_true",
        dest="use_graph",
        help="Orkestrasi retrieve/decide/generate/verify dengan LangGraph",
    )
    p_ask.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Tampilkan chunk yang diambil (debug)",
    )

    # ── list ──
    sub.add_parser(
        "list",
        help="Tampilkan semua dokumen di workspace",
    )

    # ── delete ──
    p_delete = sub.add_parser(
        "delete",
        help="Hapus dokumen dari workspace",
    )
    p_delete.add_argument(
        "doc_id",
        metavar="DOC_ID",
        help="doc_id yang akan dihapus (lihat dari perintah list)",
    )
    p_delete.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Konfirmasi otomatis (tidak bertanya)",
    )

    # ── eval ──
    p_eval = sub.add_parser(
        "eval",
        help="Bandingkan baseline A (seluruh dokumen), B (hybrid), dan C (Neo4j)",
    )
    p_eval.add_argument(
        "--questions",
        default="eval/questions.yaml",
        metavar="FILE",
        help="Dataset ground truth YAML (default: eval/questions.yaml)",
    )
    p_eval.add_argument(
        "--reports-dir",
        default="eval/reports",
        metavar="DIR",
        help="Direktori keluaran laporan JSON dan Markdown",
    )
    p_eval.add_argument(
        "--baseline",
        action="append",
        choices=("A", "B", "C"),
        dest="baselines",
        help="Baseline yang dijalankan; ulangi opsi untuk memilih lebih dari satu",
    )
    p_eval.add_argument(
        "--max-retries",
        type=int,
        default=0,
        help="Retry jawaban setelah verifikasi sitasi gagal (default: 0)",
    )
    p_eval.add_argument(
        "--no-judge",
        action="store_false",
        dest="use_judge",
        help="Lewati penilaian correctness dan faithfulness oleh LLM",
    )
    p_eval.add_argument(
        "--validate-only",
        action="store_true",
        help="Validasi dataset tanpa memanggil embedding, retrieval, atau LLM",
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    workspace = args.workspace  # bisa None, command akan baca env WORKSPACE

    if args.command == "probe-embedding":
        from app.commands.probe_embedding import cmd_probe_embedding
        cmd_probe_embedding()

    elif args.command == "ingest":
        from app.commands.ingest import cmd_ingest
        cmd_ingest(
            files=args.files or None,
            workspace=workspace,
            force=args.force,
        )

    elif args.command == "ask":
        from app.commands.ask import cmd_ask
        cmd_ask(
            question=args.question,
            workspace=workspace,
            return_parent=args.return_parent,
            verbose=args.verbose,
            use_graph=args.use_graph,
        )

    elif args.command == "list":
        from app.commands.list_docs import cmd_list
        cmd_list(workspace=workspace)

    elif args.command == "delete":
        from app.commands.delete import cmd_delete
        cmd_delete(
            doc_id=args.doc_id,
            workspace=workspace,
            yes=args.yes,
        )

    elif args.command == "eval":
        from app.commands.eval import cmd_eval
        cmd_eval(
            questions_path=args.questions,
            reports_dir=args.reports_dir,
            workspace=workspace,
            baselines=args.baselines,
            max_retries=args.max_retries,
            use_judge=args.use_judge,
            validate_only=args.validate_only,
        )

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
