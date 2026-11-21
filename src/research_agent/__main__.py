"""Command-line entry point for local environment checks."""

import argparse
import json
import sys
from urllib.request import urlopen

from research_agent.config import OllamaSettings


def doctor(settings: OllamaSettings) -> None:
    with urlopen(f"{settings.url}/api/tags", timeout=min(5, settings.timeout)) as response:
        models = json.load(response)["models"]
    if not any(model.get("name") == settings.model for model in models):
        raise ValueError(f"Installed Ollama models do not include {settings.model}")
    print(f"Python {sys.version.split()[0]} | Ollama reachable | model {settings.model} installed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Local technical research agent tools")
    parser.add_argument("command", choices=["doctor"], help="check the local Ollama environment")
    parser.parse_args()
    try:
        doctor(OllamaSettings.from_env())
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Environment check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
