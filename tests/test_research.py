import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from urllib.error import HTTPError

from research_agent.agent.planning import Task, TaskManager
from research_agent.llm.base import BaseLLM, ChatResponse, Message
from research_agent.memory import TaskMemory
from research_agent.research.report import Evidence, check_findings, resolve_citations, review_decisions, review_messages
from research_agent.research.web import Article, Wikipedia
from research_agent.research.workflow import ResearchWorkflow
from research_agent.tools.base import ToolError
from research_agent.tools.search import SearchHit


class CitationTests(unittest.TestCase):
    def test_resolves_real_excerpts_and_rejects_unknown_ids(self):
        source = Evidence("E1", "notes.pdf", "p. 2", "We study general category discovery.")
        claim = {"kind": "finding", "statement": "The paper studies category discovery.", "references": ["E1"]}
        data = {"findings": [claim, {**claim, "references": ["E99"]}], "gap": ""}
        accepted, _, rejected = resolve_citations(data, (source,))
        self.assertEqual(accepted[0]["references"], [{"id": "E1", "quote": source.text}])
        self.assertEqual(rejected, 1)

    def test_review_shares_source_text_without_cross_granting_references(self):
        sources = (Evidence("E1", "a.txt", "line 1", "Shared evidence"),
                   Evidence("E2", "b.txt", "line 1", "Second evidence"),
                   Evidence("E3", "c.txt", "line 1", "Uncited evidence"))
        claims = [
            {"kind": "finding", "statement": "A", "references": [{"id": "E1", "quote": "..."}]},
            {"kind": "finding", "statement": "B", "references": [{"id": "E1", "quote": "..."},
                                                             {"id": "E2", "quote": "..."}]},
        ]
        payload = json.loads(review_messages("Question", claims, sources)[1].content)
        self.assertEqual(payload["sources"], {"E1": "Shared evidence", "E2": "Second evidence"})
        self.assertEqual([candidate["citation_ids"] for candidate in payload["candidates"]],
                         [["E1"], ["E1", "E2"]])

    def test_review_requires_all_candidates_and_drops_unsupported_statements(self):
        findings = [{"statement": "A"}, {"statement": "B"}]
        decisions = {"decisions": [{"number": 2, "supported": True}, {"number": 1, "supported": False}]}
        self.assertEqual(review_decisions(decisions, findings), [findings[1]])
        with self.assertRaises(ValueError):
            review_decisions({"decisions": decisions["decisions"][:1]}, findings)

    def test_rejects_invented_references_and_quotes(self):
        evidence = (Evidence("E1", "notes.md", "lines 1–2", "A checkpoint copies committed changes."),)
        accepted = {"kind": "finding", "statement": "A checkpoint copies changes.",
                    "references": [{"id": "E1", "quote": "copies committed changes"}]}
        for reference in ({"id": "E2", "quote": "copies committed changes"},
                          {"id": "E1", "quote": "deletes all changes"}):
            findings, gap, count = check_findings(
                {"findings": [accepted, {**accepted, "references": [reference]}], "gap": "Scope unclear"},
                evidence,
            )
            self.assertEqual((findings, gap, count), ([accepted], "Scope unclear", 1))

    def test_conflict_requires_two_distinct_sources(self):
        sources = (
            Evidence("E1", "notes.md", "lines 1–2", "Checkpoint can be delayed."),
            Evidence("E2", "notes.md", "lines 3–4", "Checkpoint cannot be delayed."),
        )
        data = {"gap": "", "findings": [{"kind": "conflict", "statement": "Sources disagree.",
                "references": [{"id": "E1", "quote": sources[0].text}, {"id": "E2", "quote": sources[1].text}]}]}
        self.assertEqual(check_findings(data, sources)[2], 1)
        self.assertEqual(check_findings(data, (sources[0], Evidence("E2", "other.md", "lines 1–1",
                                                                  sources[1].text)))[2], 0)


class WikipediaTests(unittest.TestCase):
    def test_search_shapes_results_and_fetch_returns_revision(self):
        client = Wikipedia("https://example.test/contact")
        client.opener = Mock()
        client.opener.open.side_effect = [
            io.BytesIO(json.dumps({"query": {"search": [{"pageid": 5, "title": "WAL",
                "snippet": '<span class="searchmatch">WAL</span> &amp; SQLite'}]}}).encode()),
            io.BytesIO(json.dumps({"query": {"pages": [{"title": "WAL", "lastrevid": 12,
                "extract": "Writes log records."}]}}).encode()),
        ]
        hit, = client.search("write ahead", limit=2, timeout=3)
        self.assertEqual(hit.snippet, "WAL & SQLite")
        self.assertEqual(client.fetch(hit.url), Article("WAL", "https://en.wikipedia.org/?oldid=12",
                                                        "Writes log records."))
        request = client.opener.open.call_args_list[0].args[0]
        self.assertIn("srsearch=write+ahead", request.full_url)
        self.assertEqual(request.get_header("User-agent"), "ResearchAgent/0.1 (https://example.test/contact)")

    def test_fetch_blocks_foreign_urls_and_reports_rate_limits(self):
        client = Wikipedia("https://example.test/contact")
        client.opener = Mock()
        with self.assertRaises(ToolError) as blocked:
            client.fetch("https://en.wikipedia.org.example.test/?curid=5")
        self.assertEqual(blocked.exception.code, "web_url_not_allowed")
        client.opener.open.assert_not_called()
        client.opener.open.side_effect = HTTPError("https://en.wikipedia.org/", 429, "", {}, None)
        with self.assertRaises(ToolError) as limit:
            client.search("SQLite", limit=2, timeout=3)
        self.assertEqual(limit.exception.code, "web_rate_limited")


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(temporary.cleanup)
        self.memory = TaskMemory(Path(temporary.name) / "memory.sqlite3")
        self.run = self.memory.load(self.memory.create("SQLite", TaskManager((Task("wal", "What is WAL?"),))))
        self.model = Mock(spec=BaseLLM)
        self.embedder = Mock()
        self.web = Mock(spec=Wikipedia)

    def test_online_evidence_report_and_resume_use_persisted_results(self):
        self.web.search.return_value = [SearchHit("SQLite", "https://en.wikipedia.org/?curid=5", "SQLite")]
        self.web.fetch.return_value = Article("SQLite", "https://en.wikipedia.org/?oldid=12",
                                             "SQLite uses a write-ahead log.")
        analysis = ChatResponse(Message("assistant", json.dumps({
            "findings": [{"kind": "finding", "statement": "SQLite can write to a WAL.",
                          "references": ["E1"]}], "gap": "",
        })), True)
        review = ChatResponse(Message("assistant", '{"decisions":[{"number":1,"supported":true}]}'), True)
        self.model.chat.side_effect = [analysis, review]
        workflow = ResearchWorkflow(self.model, self.memory, embedder=self.embedder, web=self.web)
        report, count, states = workflow.run(self.run)
        self.assertEqual(count, 1)
        self.assertEqual(states["wal"].status, "succeeded")
        self.assertIn("[S1]", report)
        self.assertIn("https://en.wikipedia.org/?oldid=12", report)
        self.assertEqual(len(self.memory.messages(self.run.id)), 6)
        self.assertEqual(workflow.run(self.run), (report, count, states))
        self.assertEqual(self.model.chat.call_count, 2)
        self.web.fetch.assert_called_once()
        self.embedder.assert_not_called()

    def test_failed_web_search_yields_gap_instead_of_unsupported_claim(self):
        self.web.search.side_effect = ToolError("web_rate_limited", "wait")
        report, count, _states = ResearchWorkflow(self.model, self.memory, embedder=self.embedder,
                                                   web=self.web).run(self.run)
        self.assertEqual(count, 0)
        self.assertIn("web\\_rate\\_limited", report)
        self.assertIn("没有可用", report)
        self.model.chat.assert_not_called()
