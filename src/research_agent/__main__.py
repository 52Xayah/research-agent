"""Command-line entry point for model checks and local tool demos."""

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from urllib.request import urlopen

from research_agent.agent.demo import run_demo
from research_agent.agent.planning import Planner
from research_agent.config import OllamaSettings
from research_agent.function_demo import run_examples
from research_agent.llm.base import LLMError, ToolCall
from research_agent.llm.ollama import OllamaLLM
from research_agent.llm.probe import run_probe
from research_agent.memory import TaskMemory
from research_agent.rag.documents import load_corpus
from research_agent.rag.index import KnowledgeBase, local_embedder
from research_agent.tools.calculator import Calculator
from research_agent.tools.file_reader import FileReader
from research_agent.tools.registry import ToolRegistry
from research_agent.tools.search import Search


def doctor(settings: OllamaSettings) -> None:
    with urlopen(f"{settings.url}/api/tags", timeout=min(5, settings.timeout)) as response:
        data = json.load(response)
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, list) or not all(isinstance(model, dict) for model in models):
        raise ValueError("Ollama returned an invalid model list")
    if not any(model.get("name") == settings.model for model in models):
        raise ValueError(f"Installed Ollama models do not include {settings.model}")
    print(f"Python {sys.version.split()[0]} | Ollama reachable | model {settings.model} installed")


def run_tool(name: str, root: Path | None) -> int:
    registry = ToolRegistry()
    registry.register(Calculator())
    registry.register(Search())
    if name == FileReader.name:
        if root is None:
            raise ValueError("read_file requires --root to authorize a directory")
        registry.register(FileReader(root))
    arguments = json.load(sys.stdin)
    result = registry.dispatch(ToolCall(name, arguments))
    print(json.dumps(result.as_dict(), ensure_ascii=False, allow_nan=False))
    return 0 if result.ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Local technical research agent tools")
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="check the local Ollama environment")
    commands.add_parser("model-check", help="run live Ollama capability checks")
    commands.add_parser("function-demo", help="run a single live tool call with result feedback")
    commands.add_parser("function-check", help="evaluate live tool calling on six fixed examples")
    agent_command = commands.add_parser("agent-demo", help="run a live multi-tool Agent Loop")
    agent_command.add_argument("--root", type=Path, default=Path("examples"), help="demo input directory")
    plan_command = commands.add_parser("plan", help="generate and validate a research plan")
    plan_command.add_argument("topic")
    history_command = commands.add_parser("history", help="list or inspect saved research runs")
    history_command.add_argument("run_id", nargs="?")
    history_command.add_argument("--db", type=Path, default=Path(".research-agent/state.sqlite3"))
    rag_command = commands.add_parser("rag-search", help="index an authorized document directory and retrieve matches")
    rag_command.add_argument("root", type=Path)
    rag_command.add_argument("query")
    rag_command.add_argument("--limit", type=int, default=4)
    tool_command = commands.add_parser("tool-run", help="execute a tool with JSON arguments from standard input")
    tool_command.add_argument("name", choices=[Calculator.name, FileReader.name, Search.name])
    tool_command.add_argument("--root", type=Path, help="authorized directory for read_file")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.ERROR)
    try:
        if args.command == "tool-run":
            return run_tool(args.name, args.root)
        if args.command == "history":
            memory = TaskMemory(args.db)
            if args.run_id:
                run = memory.load(args.run_id)
                data = {
                    "id": run.id, "topic": run.topic, "plan": run.plan.as_dict(),
                    "states": {key: asdict(state) for key, state in memory.states(run.id).items()},
                    "messages": [asdict(message) for message in memory.messages(run.id)],
                }
            else:
                data = memory.list_runs()
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        settings = OllamaSettings.from_env()
        if args.command == "model-check":
            return 0 if run_probe(OllamaLLM(settings)) else 1
        if args.command in {"function-demo", "function-check"}:
            return 0 if run_examples(OllamaLLM(settings), all_cases=args.command == "function-check") else 1
        if args.command == "agent-demo":
            return 0 if run_demo(OllamaLLM(settings), args.root) else 1
        if args.command == "plan":
            result = Planner(OllamaLLM(settings)).plan(args.topic)
            print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
            return 0
        if args.command == "rag-search":
            corpus = load_corpus(args.root)
            matches = KnowledgeBase(corpus.chunks, local_embedder(settings)).retrieve(args.query, args.limit)
            print(json.dumps({"matches": [asdict(match) for match in matches], "issues": corpus.issues},
                             ensure_ascii=False, indent=2))
            return 0
        doctor(settings)
    except (OSError, ValueError, KeyError, TypeError, LLMError) as error:
        print(f"{args.command} failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
