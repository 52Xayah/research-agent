"""Command-line entry point for local environment checks."""

import argparse
import json
import sys
from urllib.request import urlopen

from research_agent.config import OllamaSettings
from research_agent.llm.client import OllamaClient
from research_agent.llm.probe import run_probe


def doctor(settings: OllamaSettings) -> None:
    with urlopen(f"{settings.url}/api/tags", timeout=min(5, settings.timeout)) as response:
        models = json.load(response)["models"]
    if not any(model.get("name") == settings.model for model in models):
        raise ValueError(f"Installed Ollama models do not include {settings.model}")
    print(f"Python {sys.version.split()[0]} | Ollama reachable | model {settings.model} installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Local technical research agent tools")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="check the local Ollama environment")
    commands.add_parser("model-check", help="run live Ollama capability checks")
    args = parser.parse_args()
    try:
        settings = OllamaSettings.from_env()
        if args.command == "model-check":
            return 0 if run_probe(OllamaClient(settings)) else 1
        doctor(settings)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Environment check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
