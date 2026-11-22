import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from research_agent.llm.base import BaseLLM
from research_agent.memory import TaskMemory
from research_agent.research.outline import OUTLINE_TASK, extract_outlines, research_plan
from research_agent.research.workflow import ResearchWorkflow


@unittest.skipUnless(importlib.util.find_spec("pymupdf"), "RAG extra is missing")
class OutlineTests(unittest.TestCase):
    def test_unbookmarked_pdf_renders_numbered_sections_and_physical_pages(self):
        import pymupdf

        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            sources = root / "sources"
            papers = sources / "papers"
            papers.mkdir(parents=True)
            with pymupdf.open() as pdf:
                first = pdf.new_page()
                first.insert_text((40, 40), "1. Introduction", fontname="hebo")
                first.insert_text((40, 62), "We propose a method for assigning labels to sequences.")
                first.insert_text((40, 88), "1.1. Background", fontname="hebo")
                first.insert_text((40, 110), "The dataset contains both labelled and unlabelled examples.")
                second = pdf.new_page()
                second.insert_text((40, 40), "2. Experiments", fontname="hebo")
                second.insert_text((40, 62), "We compare accuracy on two datasets under the same protocol.")
                second.insert_text((40, 88), "References", fontname="hebo")
                second.insert_text((40, 110), "A citation entry should not replace the section list.")
                pdf.new_page()
                pdf.save(papers / "paper.pdf")

            llm = Mock(spec=BaseLLM)
            embedder = Mock()
            topic = "请列出当前上传论文的全部章节标题，并说明主要内容和页码。"
            plan = research_plan(llm, topic, sources, context="Write a different detailed research report")
            self.assertEqual([task.id for task in plan.tasks], [OUTLINE_TASK])
            memory = TaskMemory(root / "state.sqlite3")
            run = memory.load(memory.create(topic, plan, {"root": str(sources)}))
            workflow = ResearchWorkflow(llm, memory, embedder=embedder)
            report, count, states = workflow.run(run)

            self.assertEqual(count, 4)
            self.assertIn("扫描 3 页，其中 2 页含可提取文字", report)
            self.assertIn("#### 2. Experiments\n\nPDF 第 2 页", report)
            self.assertIn("##### 1.1. Background", report)
            self.assertIn("The dataset contains both labelled and unlabelled examples.", report)
            self.assertIn("papers/paper.pdf · p. 2", report)
            self.assertIn("1 页没有可提取文字", report)
            self.assertEqual(states, memory.states(run.id))
            self.assertEqual(workflow.run(run), (report, count, states))
            self.assertEqual([event["tool"] for event in memory.tool_events(run.id)], ["scan_pdf_outline"])
            llm.chat.assert_not_called()
            embedder.assert_not_called()

    def test_no_pdf_reports_the_missing_source(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            (root / "note.md").write_text("# Content", encoding="utf-8")
            outlines, issues = extract_outlines(root)
        self.assertFalse(outlines)
        self.assertIn("没有可逐页扫描", issues[0])
