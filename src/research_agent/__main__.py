"""Command-line entry point for local environment checks."""

import argparse
import json
import logging
import sys
from urllib.request import urlopen

from research_agent.config import OllamaSettings
from research_agent.function_demo import run_examples
from research_agent.llm.ollama import OllamaLLM
from research_agent.llm.probe import run_probe


def doctor(settings: OllamaSettings) -> None:
    with urlopen(f"{settings.url}/api/tags", timeout=min(5, settings.timeout)) as response:
        models = json.load(response)["models"]
    if not any(model.get("name") == settings.model for model in models):
        raise ValueError(f"Installed Ollama models do not include {settings.model}")
    print(f"Python {sys.version.split()[0]} | Ollama reachable | model {settings.model} installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Local technical research agent tools")
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="check the local Ollama environment")
    commands.add_parser("model-check", help="run live Ollama capability checks")
    commands.add_parser("function-demo", help="run a single live tool call with result feedback")
    commands.add_parser("function-check", help="evaluate live tool calling on six fixed examples")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.ERROR)
    try:
        settings = OllamaSettings.from_env()
        if args.command == "model-check":
            return 0 if run_probe(OllamaLLM(settings)) else 1
        if args.command in {"function-demo", "function-check"}:
            return 0 if run_examples(OllamaLLM(settings), all_cases=args.command == "function-check") else 1
        doctor(settings)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Environment check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
