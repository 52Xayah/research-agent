"""Command-line research runs and report export."""

import argparse
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from research_agent.config import OllamaSettings
from research_agent.llm.base import Message
from research_agent.llm.ollama import OllamaLLM
from research_agent.memory import TaskMemory
from research_agent.rag.index import local_embedder
from research_agent.research.outline import OUTLINE_TASK, research_plan
from research_agent.research.web import Wikipedia
from research_agent.research.workflow import ResearchWorkflow

DEFAULT_DB = Path(".research-agent/state.sqlite3")


def add_research_command(commands) -> None:
    parser = commands.add_parser("research", help="collect evidence and generate a cited Markdown report")
    parser.add_argument("topic", nargs="?")
    parser.add_argument("--root", type=Path, help="authorized local source directory")
    parser.add_argument("--online", action="store_true", help="enable Wikipedia search and article retrieval")
    parser.add_argument("--query", help="optional Wikipedia search expression")
    parser.add_argument("--resume", metavar="RUN_ID", help="resume using the saved plan and source settings")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, help="Markdown output path")


def run_research(args: argparse.Namespace, settings: OllamaSettings) -> int:
    model = OllamaLLM(settings)
    memory = TaskMemory(args.db)
    if args.resume:
        if args.topic or args.root or args.online or args.query is not None:
            raise ValueError("--resume uses the original topic, root and online settings")
        run = memory.load(args.resume)
        web = _web() if run.options.get("online") else None
    else:
        if not args.topic or (args.root is None and not args.online):
            raise ValueError("Provide a topic and at least one source (--root or --online)")
        if args.query is not None and (not args.online or not 1 <= len(args.query.strip()) <= 256):
            raise ValueError("--query requires --online and 1–256 characters")
        root = args.root.resolve(strict=True) if args.root is not None else None
        if root is not None and not root.is_dir():
            raise ValueError("--root must be a directory")
        web = _web() if args.online else None
        plan = research_plan(model, args.topic, root)
        run_id = memory.create(args.topic, plan, {
            "root": str(root) if root else None, "online": args.online, "query": args.query,
        })
        memory.append_messages(run_id, (Message("user", args.topic),))
        run = memory.load(run_id)
    print(f"Run: {run.id}", flush=True)
    workflow = ResearchWorkflow(model, memory, embedder=lambda: local_embedder(settings), web=web)
    report, count, states = workflow.run(run)
    output = args.output or memory.path.parent / "reports" / f"{run.id}.md"
    _write_report(output, report)
    issues = sum(state.status != "succeeded" for state in states.values())
    unit = "sections located" if OUTLINE_TASK in states else "cited findings"
    print(f"Report: {output.resolve()} | {count} {unit} | {issues} failed or blocked tasks")
    return 0 if count and not issues else 2


def _web() -> Wikipedia:
    return Wikipedia(os.getenv("RESEARCH_WIKI_CONTACT", ""))


def _write_report(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(content)
            handle.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
