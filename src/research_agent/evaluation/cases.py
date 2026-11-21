"""Fixed, bilingual tool-use benchmark."""

from dataclasses import dataclass

from research_agent.llm.base import ToolCall
from research_agent.research.report import Evidence


@dataclass(frozen=True)
class Case:
    id: str
    prompt: str
    answer: str
    calls: tuple[ToolCall, ...] = ()


CASES = (
    Case("direct", "Reply with exactly READY and do not call any tool.", "ready"),
    Case("arithmetic", "Use calculator with the exact expression 17 * 6 + 5. Reply only with the result.",
         "107", (ToolCall("calculator", {"expression": "17 * 6 + 5"}),)),
    Case("division", "Call calculator with the exact expression (18 - 3) / 5. Reply only with its result.",
         "3", (ToolCall("calculator", {"expression": "(18 - 3) / 5"}),)),
    Case("read", "Use read_file to read benchmark-note.txt. Return only the color following Color.",
         "teal", (ToolCall("read_file", {"path": "benchmark-note.txt"}),)),
    Case("read_then_calculate", "Read benchmark-note.txt using read_file first. Then pass the exact expression "
         "after Expression to calculator. Reply with the result only.", "79", (
             ToolCall("read_file", {"path": "benchmark-note.txt"}),
             ToolCall("calculator", {"expression": "9 * 8 + 7"}),
         )),
    Case("chinese", "调用 calculator，表达式严格使用 42 - 17。最终只回复数字。", "25",
         (ToolCall("calculator", {"expression": "42 - 17"}),)),
)

EVIDENCE = (
    Evidence("E1", "benchmark.md", "line 1", "A checkpoint copies committed changes back into the database."),
    Evidence("E2", "notes.txt", "line 1", "Long-lived readers can delay the progress of a checkpoint."),
)

# Each candidate is evaluated independently. The last field is the expected outcome.
CITATION_CASES = (
    ("supported", "A checkpoint copies committed changes into the database.",
     "E1", "copies committed changes back into the database", True),
    ("wrong_mechanism", "A checkpoint copies uncommitted changes into the database.",
     "E1", "copies committed changes back into the database", False),
    ("missing_id", "A checkpoint copies committed changes into the database.",
     "E3", "copies committed changes back into the database", False),
    ("invented_quote", "A checkpoint always truncates the WAL file.",
     "E1", "always truncates the WAL file", False),
)
