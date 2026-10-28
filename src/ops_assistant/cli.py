"""Command line: python -m ops_assistant <command>.

corpus        list documents in force and the versions excluded, with reasons
index         embed the chunks (OpenAI) and save the cache in data/index
ask           answer one question and print the result
serve         run the API and demo page
eval ...      retrieval experiment, answer runs, reports and the freeze check
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ops_assistant.config import Settings, load_settings
from ops_assistant.logging_setup import configure_logging

logger = logging.getLogger("ops_assistant")


def cmd_corpus(settings: Settings, _: argparse.Namespace) -> int:
    from ops_assistant.service import load_chunks

    corpus, chunks = load_chunks(settings)
    print(f"Documents in force on {corpus.as_of.isoformat()}:")
    for document in corpus.documents:
        meta = document.metadata
        count = sum(1 for c in chunks if c.doc_id == meta.doc_id)
        origin = " (external)" if meta.source == "external" else ""
        print(f"  {meta.doc_id} v{meta.version}  {meta.title}{origin}  [{count} chunks]")
    print("Excluded versions:")
    for exclusion in corpus.exclusions:
        print(f"  {exclusion.doc_id} v{exclusion.version}: {exclusion.reason}")
    print(
        f"Chunks: {len(chunks)} "
        f"({settings.chunking.strategy}, max {settings.chunking.max_words} words)"
    )
    print(f"Corpus fingerprint: {corpus.fingerprint()}")
    return 0


def cmd_index(settings: Settings, _: argparse.Namespace) -> int:
    from ops_assistant.llm.openai_provider import build_openai
    from ops_assistant.retrieval import EmbeddingCache, EmbeddingRetriever
    from ops_assistant.service import load_chunks

    _, chunks = load_chunks(settings)
    _, embedder = build_openai(settings)
    cache = EmbeddingCache(settings.embedding_cache_dir, embedder.model)
    EmbeddingRetriever(chunks, embedder, cache, settings.embedding.batch_size)
    print(f"Embedded {len(chunks)} chunks with {embedder.model}; new tokens: {cache.tokens_spent}")
    print(f"Cache: {cache.path}")
    return 0


def cmd_ask(settings: Settings, args: argparse.Namespace) -> int:
    from ops_assistant.service import build_pipeline

    pipeline = build_pipeline(settings, mode=args.mode)
    result = pipeline.service.ask(args.question, args.top_k)
    if args.json:
        from ops_assistant.api import to_response

        print(to_response(result, "cli").model_dump_json(indent=2))
        return 0
    print(f"Outcome: {result.outcome}")
    print(f"Answer: {result.answer}")
    if result.conflict_note:
        print(f"Conflict: {result.conflict_note}")
    for citation in result.citations:
        print(f"  [{citation.chunk_id}] {citation.heading}")
    for warning in result.warnings:
        print(f"Warning: {warning}")
    cost = "unknown" if result.cost_usd is None else f"${result.cost_usd:.6f}"
    print(
        f"{result.retrieval_mode} retrieval {result.timings.retrieval_ms:.0f} ms, "
        f"generation {result.timings.generation_ms:.0f} ms, model {result.model}, "
        f"tokens {result.usage.input_tokens} in / {result.usage.output_tokens} out, cost {cost}"
    )
    return 0


def cmd_serve(settings: Settings, args: argparse.Namespace) -> int:
    import uvicorn

    from ops_assistant.api import create_app

    uvicorn.run(
        create_app(settings=settings),
        host=args.host,
        port=args.port,
        log_config=None,
        # The app logs every request with its request id, so uvicorn's access log would repeat it.
        access_log=False,
    )
    return 0


def cmd_eval_freeze(settings: Settings, args: argparse.Namespace) -> int:
    from ops_assistant.evaluation.cases import check_freeze, write_freeze

    path = settings.root / "eval" / "frozen_cases.jsonl"
    if args.check:
        print(f"{path.name} matches its freeze: {check_freeze(path)}")
    else:
        print(f"Froze {path.name}: {write_freeze(path)}")
    return 0


def cmd_eval_retrieval(settings: Settings, args: argparse.Namespace) -> int:
    from ops_assistant.evaluation.report import write_retrieval_report
    from ops_assistant.evaluation.runner import ChunkingConfig, run_retrieval_experiment
    from ops_assistant.retrieval import needs_embeddings

    modes = args.modes.split(",")
    embedder = None
    if any(needs_embeddings(m) for m in modes):
        from ops_assistant.llm.openai_provider import build_openai

        _, embedder = build_openai(settings)
    chunkings = [ChunkingConfig.parse(c) for c in args.chunking.split(",")]
    run_dir = run_retrieval_experiment(settings, args.set, modes, chunkings, args.k, embedder)
    summary = write_retrieval_report(run_dir)
    print(f"Results: {summary}")
    return 0


def cmd_eval_answers(settings: Settings, args: argparse.Namespace) -> int:
    from ops_assistant.evaluation.report import write_answer_report
    from ops_assistant.evaluation.runner import AnswerRunOptions, run_answers

    mode = args.mode or settings.retrieval.mode
    options = AnswerRunOptions(args.set, mode, args.limit, tuple(args.case or ()))
    run_dir = run_answers(settings, options)
    summary = write_answer_report(run_dir)
    print(f"Results: {summary}")
    print(f"Review sheet: {run_dir / 'review.csv'}")
    return 0


def cmd_eval_report(_: Settings, args: argparse.Namespace) -> int:
    from ops_assistant.evaluation.report import write_answer_report, write_retrieval_report

    run_dir = Path(args.run_dir)
    if (run_dir / "per_case.csv").exists():
        summary = write_retrieval_report(run_dir)
    else:
        summary = write_answer_report(run_dir, Path(args.review) if args.review else None)
    print(f"Results: {summary}")
    return 0


def cmd_eval_publish(settings: Settings, args: argparse.Namespace) -> int:
    from ops_assistant.evaluation.publish import publish

    review = Path(args.review) if args.review else None
    publish(settings.root / "README.md", Path(args.answers), Path(args.retrieval), review)
    print("Updated README.md results and docs/results/")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ops_assistant", description=__doc__.splitlines()[0])
    parser.add_argument("--settings", type=Path, help="path to settings.toml")
    parser.add_argument("--log-level", help="default INFO for serve, WARNING otherwise")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("corpus", help="show the documents in force").set_defaults(run=cmd_corpus)
    commands.add_parser("index", help="build the embedding cache").set_defaults(run=cmd_index)

    ask = commands.add_parser("ask", help="answer one question")
    ask.add_argument("question")
    ask.add_argument("--mode", choices=["keyword", "embedding", "hybrid"])
    ask.add_argument("--top-k", type=int)
    ask.add_argument("--json", action="store_true", help="print the API response body")
    ask.set_defaults(run=cmd_ask)

    serve = commands.add_parser("serve", help="run the API and demo page")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(run=cmd_serve)

    evaluation = commands.add_parser("eval", help="evaluation commands")
    eval_commands = evaluation.add_subparsers(dest="eval_command", required=True)

    freeze = eval_commands.add_parser("freeze", help="record or check the frozen set's hash")
    freeze.add_argument("--check", action="store_true")
    freeze.set_defaults(run=cmd_eval_freeze)

    retrieval = eval_commands.add_parser("retrieval", help="compare retrieval configurations")
    retrieval.add_argument("--set", choices=["dev", "frozen"], default="dev")
    retrieval.add_argument("--modes", default="keyword,embedding,hybrid")
    retrieval.add_argument(
        "--chunking",
        default="section:160:40,section:40:10,window:80:20,window:160:40,window:320:60",
        help="comma-separated strategy:max_words:overlap_words; the first is the reference",
    )
    retrieval.add_argument("--k", type=int, default=5)
    retrieval.set_defaults(run=cmd_eval_retrieval)

    answers = eval_commands.add_parser("answers", help="run the answer evaluation")
    answers.add_argument("--set", choices=["dev", "frozen"], default="dev")
    answers.add_argument("--mode", choices=["keyword", "embedding", "hybrid"])
    answers.add_argument("--limit", type=int)
    answers.add_argument("--case", action="append", help="run only this case id (repeatable)")
    answers.set_defaults(run=cmd_eval_answers)

    report = eval_commands.add_parser("report", help="rebuild a run's summary.md")
    report.add_argument("run_dir")
    report.add_argument("--review", help="completed review.csv to include")
    report.set_defaults(run=cmd_eval_report)

    publish = eval_commands.add_parser("publish", help="write headline results into README.md")
    publish.add_argument("--answers", required=True, help="frozen answer run folder")
    publish.add_argument("--retrieval", required=True, help="frozen retrieval run folder")
    publish.add_argument("--review", help="completed review.csv for the answer run")
    publish.set_defaults(run=cmd_eval_publish)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    serving = args.command == "serve"
    args.log_level = (args.log_level or ("INFO" if serving else "WARNING")).upper()
    configure_logging(args.log_level, json_lines=serving)
    settings = load_settings(args.settings)
    try:
        return args.run(settings, args)
    except Exception as error:
        category = getattr(error, "category", type(error).__name__)
        print(f"Error ({category}): {error}", file=sys.stderr)
        if args.log_level == "DEBUG":
            raise
        return 1


if __name__ == "__main__":
    sys.exit(main())
