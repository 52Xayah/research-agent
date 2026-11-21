import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from research_agent.llm.base import ToolCall
from research_agent.parameters import Parameter
from research_agent.tools.base import BaseTool, ToolError
from research_agent.tools.calculator import Calculator
from research_agent.tools.file_reader import FileReader
from research_agent.tools.registry import ToolRegistry
from research_agent.tools.search import Search, SearchHit, SearchProvider


class ExampleTool(BaseTool):
    name = "example"
    description = "Return input"
    parameters = {"value": Parameter("integer", "Input")}

    def execute(self, *, value):
        return {"result": value}


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.tool = ExampleTool()
        self.tool.execute = Mock(wraps=self.tool.execute)
        self.registry.register(self.tool)

    def test_register_query_and_dispatch(self):
        self.assertIs(self.registry.get("example"), self.tool)
        self.assertEqual(self.registry.specs(), (self.tool.spec(),))
        self.assertEqual(self.registry.dispatch(ToolCall("example", {"value": 7})).as_dict(),
                         {"tool": "example", "ok": True, "data": {"result": 7}})
        self.tool.execute.assert_called_once_with(value=7)
        with self.assertRaisesRegex(ValueError, "already registered"):
            self.registry.register(ExampleTool())

    def test_unknown_tool_and_invalid_arguments(self):
        self.assertEqual(self.registry.dispatch(ToolCall("missing", {})).error.code, "unknown_tool")
        result = self.registry.dispatch(ToolCall("example", {"value": "7"}))
        self.assertEqual(result.as_dict(), {
            "tool": "example", "ok": False,
            "error": {"code": "invalid_arguments", "message": "value must have type integer"},
        })
        self.tool.execute.assert_not_called()

    def test_normalizes_expected_and_unexpected_errors(self):
        self.tool.execute.side_effect = ToolError("test_error", "Expected failure")
        self.assertEqual(self.registry.dispatch(ToolCall("example", {"value": 1})).error.code, "test_error")
        self.tool.execute.side_effect = OSError("private provider information")
        with self.assertLogs("research_agent.tools.registry", "WARNING") as captured:
            result = self.registry.dispatch(ToolCall("example", {"value": 1}))
        self.assertEqual(result.error.code, "execution_error")
        self.assertNotIn("private", result.error.message)
        self.assertNotIn("private", "\n".join(captured.output))

    def test_rejects_non_json_tool_result(self):
        self.tool.execute.return_value = {"result": float("nan")}
        with self.assertLogs("research_agent.tools.registry", "WARNING"):
            result = self.registry.dispatch(ToolCall("example", {"value": 1}))
        self.assertEqual(result.error.code, "execution_error")


class CalculatorTests(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.registry.register(Calculator())

    def calculate(self, expression):
        return self.registry.dispatch(ToolCall("calculator", {"expression": expression}))

    def test_basic_arithmetic(self):
        for expression, value in (("(5 + 7) * 3 - 2 ** 3", 28), ("-5 / 2", -2.5),
                                  ("13 // 2 + 13 % 2", 7), ("2 ** -2", 0.25)):
            with self.subTest(expression=expression):
                self.assertEqual(self.calculate(expression).data, {"value": value})

    def test_rejects_non_arithmetic_input(self):
        for expression in ("abs(1)", "x + 2", "True", "1 < 2", "(2).__class__", "10 & 2", "1+"):
            with self.subTest(expression=expression):
                self.assertEqual(self.calculate(expression).error.code, "invalid_expression")

    def test_enforces_expression_and_numeric_limits(self):
        for expression, code in (
            ("3 ** 99", "numeric_limit"),
            ("1e999", "numeric_limit"),
            ("1e90 * 1e90", "numeric_limit"),
            ("3 ** 0.5", "numeric_limit"),
            ("1 / 0", "division_by_zero"),
            ("9" * 257, "invalid_arguments"),
            ("+".join(["1"] * 40), "invalid_expression"),
        ):
            with self.subTest(expression=expression):
                self.assertEqual(self.calculate(expression).error.code, code)


class FileReaderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        self.root = self.workspace / "docs"
        self.root.mkdir()
        self.registry = ToolRegistry()
        self.registry.register(FileReader(self.root, max_bytes=32))

    def read(self, path):
        return self.registry.dispatch(ToolCall("read_file", {"path": path}))

    def test_reads_utf8_and_bom(self):
        folder = self.root / "notes"
        folder.mkdir()
        (folder / "报告.MD").write_text("中文", encoding="utf-8-sig")
        result = self.read(r"notes\报告.MD")
        self.assertEqual(result.data, {"path": "notes/报告.MD", "content": "中文"})
        (self.root / "small.txt").write_bytes(b"x" * 32)
        self.assertEqual(self.read("small.txt").data["content"], "x" * 32)

    def test_rejects_paths_outside_authorized_root(self):
        outside = self.workspace / "outside.txt"
        outside.write_text("excluded", encoding="utf-8")
        for path in ("../outside.txt", str(outside), r"C:outside.txt", r"\\server\share\x.txt",
                     "valid.txt:stream", "CON.txt"):
            with self.subTest(path=path):
                self.assertEqual(self.read(path).error.code, "invalid_path")

    def test_rejects_symlink_to_outside_file(self):
        outside = self.workspace / "outside.txt"
        outside.write_text("excluded", encoding="utf-8")
        try:
            (self.root / "linked.txt").symlink_to(outside)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"Could not create a symlink on this host: {error}")
        self.assertEqual(self.read("linked.txt").error.code, "path_not_allowed")

    def test_reports_unsupported_missing_large_and_invalid_text(self):
        (self.root / "invalid.txt").write_bytes(b"\xff")
        (self.root / "large.txt").write_bytes(b"x" * 33)
        (self.root / "folder.md").mkdir()
        for path, code in (("doc.pdf", "unsupported_format"), ("missing.txt", "file_not_found"),
                           ("invalid.txt", "invalid_encoding"), ("large.txt", "file_too_large"),
                           ("folder.md", "unsupported_format")):
            with self.subTest(path=path):
                self.assertEqual(self.read(path).error.code, code)


class SearchTests(unittest.TestCase):
    def test_search_requires_provider(self):
        registry = ToolRegistry()
        registry.register(Search())
        result = registry.dispatch(ToolCall("search", {"query": "SQLite"}))
        self.assertEqual(result.error.code, "search_not_configured")

    def test_forwards_limits_and_formats_results(self):
        registry = ToolRegistry()
        provider = Mock(spec=SearchProvider)
        provider.search.return_value = [
            SearchHit("SQLite", "https://example.test/1", "First"),
            SearchHit("WAL", "https://example.test/2", "Second"),
        ]
        registry.register(Search(provider, timeout=3))
        result = registry.dispatch(ToolCall("search", {"query": " SQLite ", "limit": 1}))
        provider.search.assert_called_once_with("SQLite", limit=1, timeout=3)
        self.assertEqual(result.data, {
            "query": "SQLite",
            "results": [{"title": "SQLite", "url": "https://example.test/1", "snippet": "First"}],
        })

    def test_validates_input_and_handles_timeout(self):
        registry = ToolRegistry()
        provider = Mock(spec=SearchProvider)
        registry.register(Search(provider))
        for arguments in ({"query": " "}, {"query": "SQLite", "limit": 11}):
            self.assertEqual(registry.dispatch(ToolCall("search", arguments)).error.code, "invalid_arguments")
        provider.search.assert_not_called()
        provider.search.side_effect = TimeoutError()
        result = registry.dispatch(ToolCall("search", {"query": "SQLite"}))
        self.assertEqual(result.error.code, "search_timeout")
        provider.search.assert_called_once_with("SQLite", limit=5, timeout=10)
