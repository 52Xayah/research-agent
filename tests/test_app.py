import importlib.util
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from research_agent.agent.executor import TaskState
from research_agent.agent.planning import Task, TaskManager
from research_agent.app.storage import AppStorage, QueueFull, document_name

HAS_API = all(importlib.util.find_spec(module) for module in ("fastapi", "httpx"))
HERE = Path(__file__).resolve().parent


class AppStorageTests(unittest.TestCase):
    def test_document_names_are_safe_on_windows(self):
        self.assertEqual(document_name("技术笔记.md"), "技术笔记.md")
        for name in ("../secret.txt", r"C:\note.txt", "CON.txt", ".hidden.md", "note.txt:a", "no.exe"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                document_name(name)

    def test_queue_capacity_and_restart_recovery(self):
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            storage = AppStorage(Path(folder))
            jobs = [storage.enqueue(f"Job {index}", {}) for index in range(4)]
            with self.assertRaises(QueueFull):
                storage.enqueue("Too many", {})
            storage.interrupt_pending()
            self.assertEqual([storage.get(item)["status"] for item in jobs], ["interrupted"] * 4)
            storage.resume(jobs[0])
            self.assertEqual(storage.get(jobs[0])["status"], "queued")


@unittest.skipUnless(HAS_API, "Install the app and test extras")
class ApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from research_agent.app.api import create_app

        temporary = tempfile.TemporaryDirectory(dir=HERE)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.client = self.enterContext(TestClient(create_app(self.root), base_url="http://127.0.0.1"))

    @staticmethod
    def _workflow(_llm, memory, **kwargs):
        class Workflow:
            def run(self, record):
                state = TaskState("succeeded", 1, {"ok": True})
                memory.checkpoint(record.id, "a", state)
                memory.record_tool(record.id, "retrieve", True, "1 candidate")
                return "# Sample report\n", 1, {"a": state}
        return Workflow()

    @patch("research_agent.app.service.ResearchWorkflow")
    @patch("research_agent.app.service.Planner")
    def test_upload_submit_status_history_follow_up_and_report(self, planner, workflow):
        planner.return_value.plan.return_value = TaskManager((Task("a", "Question"),))
        workflow.side_effect = self._workflow
        uploaded = self.client.post("/documents", params={"name": "note.md"}, content=b"source",
                                    headers={"Content-Type": "application/octet-stream"})
        self.assertEqual(uploaded.status_code, 201)
        job = self.client.post("/jobs", json={"topic": "Test topic", "documents": [uploaded.json()["id"]]})
        self.assertEqual(job.status_code, 202, job.text)
        key = job.json()["id"]
        finished = self._finished(key)
        self.assertEqual(finished["status"], "completed")
        self.assertEqual(finished["tasks"][0]["attempts"], 1)
        self.assertEqual(finished["tools"][0]["tool"], "retrieve")
        self.assertEqual((self.root / "sources" / key / "note.md").read_bytes(), b"source")
        self.assertEqual(self.client.get("/jobs").json()[0]["id"], key)
        report = self.client.get(f"/jobs/{key}/report?download=true")
        self.assertEqual(report.text, "# Sample report\n")
        self.assertIn("attachment;", report.headers["Content-Disposition"])
        follow_up = self.client.post("/jobs", json={"topic": "Follow-up", "parent_id": key})
        self.assertEqual(follow_up.status_code, 202)
        next_job = self._finished(follow_up.json()["id"])
        self.assertEqual(next_job["documents"], finished["documents"])
        self.assertIn("Previous topic for context: Test topic", planner.return_value.plan.call_args.args[0])

    def _finished(self, key):
        end = time.monotonic() + 5
        while time.monotonic() < end:
            response = self.client.get(f"/jobs/{key}")
            self.assertEqual(response.status_code, 200)
            result = response.json()
            if result["status"] not in {"queued", "running"}:
                return result
            time.sleep(0.01)
        self.fail("Job was not completed")

    def test_invalid_sources_and_oversized_upload_are_rejected(self):
        headers = {"Content-Type": "application/octet-stream"}
        self.assertEqual(self.client.post("/jobs", json={"topic": "No sources"}).status_code, 422)
        self.assertEqual(self.client.post("/jobs", json={"topic": "Unknown", "documents": ["0" * 32]}).status_code, 422)
        self.assertEqual(self.client.post("/documents", params={"name": "../outside.txt"},
                                          content=b"source", headers=headers).status_code, 422)
        invalid = self.client.post("/documents", params={"name": "note.txt"}, content=b"no type")
        self.assertEqual(invalid.status_code, 415)
        with patch("research_agent.app.api.MAX_FILE_BYTES", 4):
            response = self.client.post("/documents", params={"name": "big.txt"}, content=b"12345", headers=headers)
        self.assertEqual(response.status_code, 413)
        self.assertEqual(list((self.root / "uploads").iterdir()), [])

    def test_cross_origin_changes_are_rejected(self):
        response = self.client.post("/jobs", headers={"Origin": "https://other.example"}, json={"topic": "A"})
        self.assertEqual(response.status_code, 403)
