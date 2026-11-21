"""Single-worker research service shared by the API endpoints."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from research_agent.agent.planning import Planner
from research_agent.app.storage import AppStorage
from research_agent.config import OllamaSettings
from research_agent.llm.base import LLMError, Message
from research_agent.llm.ollama import OllamaLLM
from research_agent.memory import TaskMemory
from research_agent.rag.index import local_embedder
from research_agent.research.web import Wikipedia
from research_agent.research.workflow import ResearchWorkflow

logger = logging.getLogger(__name__)


class JobService:
    def __init__(self, storage: AppStorage, settings: OllamaSettings):
        self.storage = storage
        self.settings = settings
        self.memory = TaskMemory(storage.root / "research.sqlite3")
        self.storage.interrupt_pending()
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="research-worker")

    def close(self) -> None:
        self.worker.shutdown(wait=True, cancel_futures=True)

    def create(self, topic: str, uploads: list[str], online: bool,
               query: str | None, parent_id: str | None) -> dict:
        topic = topic.strip()
        if not topic:
            raise ValueError("Enter a research topic")
        if query is not None:
            query = query.strip()
            if not online or not query:
                raise ValueError("A search expression requires online research")
        parent = self.storage.get(parent_id) if parent_id else None
        if parent is not None:
            inherited = [item["id"] for item in parent["options"]["documents"]]
            uploads = list(dict.fromkeys([*inherited, *uploads]))
        docs = self.storage.documents(uploads)
        if not docs and not online:
            raise ValueError("Upload a document or explicitly enable Wikipedia search")
        if online:
            Wikipedia(os.getenv("RESEARCH_WIKI_CONTACT", ""))
        key = self.storage.enqueue(topic, {"documents": docs, "online": online, "query": query,
                                           "parent_id": parent_id, "prior_topic": parent["topic"] if parent else None})
        self.worker.submit(self._execute, key)
        return self.describe(key)

    def resume(self, key: str) -> dict:
        job = self.storage.get(key)
        if job["options"]["online"]:
            Wikipedia(os.getenv("RESEARCH_WIKI_CONTACT", ""))
        self.storage.resume(key)
        self.worker.submit(self._execute, key)
        return self.describe(key)

    def describe(self, key: str) -> dict:
        job = self.storage.get(key)
        payload = {field: job[field] for field in ("id", "topic", "status", "created_at", "error", "run_id")}
        payload.update({"documents": job["options"]["documents"], "online": job["options"]["online"],
                        "parent_id": job["options"].get("parent_id"), "report_ready": job["report"] is not None,
                        "tasks": [], "tools": []})
        if run_id := job["run_id"]:
            run = self.memory.load(run_id)
            states = self.memory.states(run_id)
            for task in run.plan.tasks:
                state = states.get(task.id)
                payload["tasks"].append({**asdict(task), "status": state.status if state else "pending",
                                         "attempts": state.attempts if state else 0,
                                         "error": state.error if state else None})
            payload["tools"] = self.memory.tool_events(run_id)
        return payload

    def _execute(self, key: str) -> None:
        try:
            self.storage.update(key, "running")
            job = self.storage.get(key)
            options = job["options"]
            llm = OllamaLLM(self.settings)
            web = Wikipedia(os.getenv("RESEARCH_WIKI_CONTACT", "")) if options["online"] else None
            run_id = job["run_id"]
            if run_id is None:
                root = self.storage.stage(key, options["documents"])
                goal = job["topic"]
                if options["prior_topic"] and len(goal) < 240:
                    goal = (f"{goal}\nPrevious topic for context: {options['prior_topic']}")[:300]
                plan = Planner(llm).plan(goal)
                run_id = self.memory.create(job["topic"], plan, {
                    "root": str(root) if root else None, "online": options["online"], "query": options["query"],
                })
                self.storage.update(key, "running", run_id=run_id)
                self.memory.append_messages(run_id, (Message("user", job["topic"]),))
            workflow = ResearchWorkflow(llm, self.memory, embedder=lambda: local_embedder(self.settings), web=web)
            report, count, states = workflow.run(self.memory.load(run_id))
            status = "completed" if count and all(state.status == "succeeded" for state in states.values()) else "partial"
            self.storage.update(key, status, report=report)
        except (OSError, LLMError, ValueError) as error:
            logger.warning("Research job %s failed (%s)", key, type(error).__name__)
            message = str(error) if isinstance(error, (ValueError, LLMError)) else "Could not access the job data"
            self.storage.update(key, "failed", error=message[:300])
        except Exception:
            logger.exception("Unexpected error in research job %s", key)
            self.storage.update(key, "failed", error="Unexpected research worker error")
