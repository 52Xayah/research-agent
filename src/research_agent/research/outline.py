"""Extract PDF headings and page-anchored section excerpts in document order."""

import re
from dataclasses import asdict, dataclass
from itertools import islice
from pathlib import Path

from research_agent.agent.planning import Planner, Task, TaskManager
from research_agent.llm.base import BaseLLM, JsonObject
from research_agent.rag.documents import MAX_FILES, MAX_TEXT_CHARS, document_paths, open_pdf

OUTLINE_TASK = "document-outline"
_OUTLINE_QUERY = re.compile(
    r"章节(?:标题|清单|目录)|各章节|每个章节|全部章节|所有章节|每一章|逐章|逐节|"
    r"(?:列出|提取|整理|查看)\s*(?:全文|论文|文章|文档)?\s*(?:的)?\s*目录|"
    r"(?:论文|文章|文档)的?目录|"
    r"\b(?:table of contents|(?:section|chapter) (?:headings|titles)|all (?:sections|chapters)|"
    r"each (?:section|chapter)|section.by.section|chapter.by.chapter)\b",
    re.I,
)
_NUMBERED = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,3})[.)、]?\s+([^\W\d_].*)$")
_CHINESE = re.compile(r"^(?:第[一二三四五六七八九十\d]+[章节篇]|[一二三四五六七八九十]+、)\s*\S")
_PARTS = re.compile(
    r"(?:abstract|acknowledge?ments?|references|bibliography|appendix(?:\s+[A-Z](?:[.:]\s*.*)?)?|"
    r"supplementary (?:material|materials)|摘要|致谢|参考文献|附录(?:[A-Z一二三四五六七八九十]|\s.*)?)",
    re.I,
)
_CAPTION = re.compile(r"^(?:fig(?:ure)?\.?|table)\s+\d|^[图表]\s*\d", re.I)
_ALGORITHM_CAPTION = re.compile(r"^(?:algorithm\s+\d+|算法\s*\d+)\s*[:：.]", re.I)
_ALGORITHM_OUTPUT = re.compile(r"^(?:output|输出)\s*[:：]", re.I)
_SENTENCE = re.compile(r"(?<!Tab\.)(?<!Fig\.)(?<!Eq\.)(?<=[.!?。！？])\s+")
_SUBSTANTIVE = re.compile(
    r"\b(?:propose|show|introduce|study|find|achiev\w*|improv\w*|outperform\w*|result\w*|"
    r"dataset\w*|method\w*|task\w*|compar\w*|performance)\b|提出|表明|结果|数据集|方法|对比",
    re.I,
)
_KEY_RESULT = re.compile(
    r"\b(?:we (?:propose|introduce|consider)|our (?:approach|method)|outperform\w*|"
    r"improv\w*|accuracy|higher|lower|margin)\b|\d\s*%|显著|我们提出",
    re.I,
)


@dataclass(frozen=True)
class _Line:
    page: int
    block: int
    text: str
    emphasized: bool
    fonts: frozenset[str]
    size: float
    bounds: tuple[float, float, float, float]
    small_number: bool


@dataclass(frozen=True)
class Excerpt:
    page: int
    text: str


@dataclass(frozen=True)
class Section:
    title: str
    level: int
    page: int
    last_page: int
    children: tuple[str, ...]
    excerpt: Excerpt | None


@dataclass(frozen=True)
class PaperOutline:
    source: str
    pages: int
    text_pages: int
    sections: tuple[Section, ...]

    def as_dict(self) -> JsonObject:
        data = asdict(self)
        data["sections"] = [
            {**section, "children": list(section["children"])} for section in data["sections"]
        ]
        return data


def research_plan(llm: BaseLLM, topic: str, root: Path | None, *, context: str | None = None) -> TaskManager:
    if root is not None and _OUTLINE_QUERY.search(topic) and next(document_paths(root, {".pdf"}), None):
        return TaskManager((Task(OUTLINE_TASK, "全文扫描 · 章节标题、主要内容与 PDF 页码"),))
    return Planner(llm).plan(topic, context=context) if context else Planner(llm).plan(topic)


def extract_outlines(root: Path) -> tuple[list[PaperOutline], list[str]]:
    root = root.resolve(strict=True)
    outlines = []
    issues = []
    paths = list(islice(document_paths(root, {".pdf"}), MAX_FILES + 1))
    if len(paths) > MAX_FILES:
        issues.append(f"仅扫描目录中的前 {MAX_FILES} 份 PDF。")
    for path in paths[:MAX_FILES]:
        source = path.relative_to(root).as_posix()
        try:
            outline = _extract_pdf(root, path)
        except (ValueError, OSError) as error:
            issues.append(f"{source} · {error}")
            continue
        outlines.append(outline)
        if outline.text_pages < outline.pages:
            issues.append(f"{source} · {outline.pages - outline.text_pages} 页没有可提取文字。")
        if not outline.sections:
            issues.append(f"{source} · 未识别到可定位的章节标题。")
    if not paths:
        issues.append("资料目录中没有可逐页扫描的 PDF。")
    return outlines, issues


def _extract_pdf(root: Path, path: Path) -> PaperOutline:
    lines: list[_Line] = []
    text_pages = 0
    size = 0
    with open_pdf(root, path) as pdf:
        import pymupdf

        flags = (pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES) | pymupdf.TEXT_DEHYPHENATE
        for number, page in enumerate(pdf, start=1):
            # Native order keeps the columns of typical journal PDFs separate.
            before = len(lines)
            for block_number, block in enumerate(page.get_text("dict", flags=flags)["blocks"]):
                for item in block.get("lines", ()):
                    spans = [span for span in item["spans"] if span["text"].strip()]
                    text = " ".join("".join(span["text"] for span in item["spans"]).split())
                    if not text or text.isdecimal():
                        continue
                    size += len(text)
                    if size > MAX_TEXT_CHARS:
                        raise ValueError("extracted PDF exceeds 100000 characters")
                    emphasized = all(span["flags"] & pymupdf.TEXT_FONT_BOLD or
                                     re.search(r"bold|medi|semibold|demi|heavy", span["font"], re.I)
                                     for span in spans)
                    font_size = max(span["size"] for span in spans)
                    leading = spans[0]
                    lines.append(_Line(
                        number, block_number, text, emphasized,
                        frozenset(span["font"] for span in spans), font_size, item["bbox"],
                        leading["text"].strip().isdecimal() and leading["size"] < 0.85 * font_size,
                    ))
            text_pages += len(lines) > before
        pages = pdf.page_count
    lines = _without_algorithm_boxes(lines)
    headings: list[tuple[int, int, int, str]] = []
    body_start = 0
    for index, line in enumerate(lines):
        if index < body_start:
            continue
        level = _heading_level(line)
        if level:
            title = line.text
            body_start = index + 1
            while body_start < len(lines) and _continues_heading(lines[body_start - 1], lines[body_start], title):
                title += " " + lines[body_start].text
                body_start += 1
            headings.append((index, body_start, level, title))
    sections = []
    for order, (start, body_start, level, title) in enumerate(headings):
        following = headings[order + 1:]
        next_heading = following[0][0] if following else len(lines)
        end = next((index for index, _, depth, _ in following if depth <= level), len(lines))
        children = tuple(text for index, _, depth, text in following if index < end and depth == level + 1)
        excerpt = None if title.casefold() in {"references", "bibliography", "参考文献"} else (
            _excerpt(lines[body_start:next_heading])
        )
        sections.append(Section(title, level, lines[start].page, lines[end - 1].page, children, excerpt))
    return PaperOutline(path.relative_to(root).as_posix(), pages, text_pages, tuple(sections))


def _heading_level(line: _Line) -> int:
    if _PARTS.fullmatch(line.text):
        return 1
    if len(line.text) > 155 or line.text.endswith((".", "。", "!", "？", "?")):
        return 0
    if match := _NUMBERED.fullmatch(line.text):
        if not line.small_number and (line.emphasized or match[2].isupper()):
            return match[1].count(".") + 1
    return int(line.emphasized and bool(_CHINESE.match(line.text)))


def _continues_heading(previous: _Line, candidate: _Line, title: str) -> bool:
    left, top, right, _ = previous.bounds
    next_left, next_top, next_right, _ = candidate.bounds
    return (
        previous.page == candidate.page
        and previous.block == candidate.block
        and previous.emphasized and candidate.emphasized
        and previous.fonts == candidate.fonts
        and abs(previous.size - candidate.size) <= 0.25
        and 0 < next_top - top <= previous.size * 1.7
        and max(left, next_left) < min(right, next_right)
        and not _heading_level(candidate)
        and not _NUMBERED.match(candidate.text)
        and not candidate.text.endswith((".", "。", "!", "？", "?"))
        and len(title) + len(candidate.text) <= 180
    )


def _without_algorithm_boxes(lines: list[_Line]) -> list[_Line]:
    excluded = set()
    for index, caption in enumerate(lines):
        if not _ALGORITHM_CAPTION.match(caption.text):
            continue
        left, top, right, _ = caption.bounds
        box = []
        for following in range(index + 1, len(lines)):
            line = lines[following]
            if line.page != caption.page:
                break
            x, y, _, _ = line.bounds
            if y < top or not left - 2 * caption.size <= x < right:
                continue
            if _ALGORITHM_CAPTION.match(line.text):
                break
            box.append(following)
            if _ALGORITHM_OUTPUT.match(line.text):
                excluded.update([index, *box])
                break
    return [line for index, line in enumerate(lines) if index not in excluded]


def _excerpt(lines: list[_Line]) -> Excerpt | None:
    index = 0
    best: Excerpt | None = None
    best_score = -1.0
    while index < len(lines):
        first = lines[index]
        group = []
        while index < len(lines) and (lines[index].page, lines[index].block) == (first.page, first.block):
            group.append(lines[index].text)
            index += 1
        text = " ".join(group)
        if len(text) < 45 or _CAPTION.match(text):
            continue
        sentences = _SENTENCE.split(text)
        for offset, sentence in enumerate(sentences):
            if len(sentence) < 45:
                continue
            excerpt = sentence
            if offset + 1 < len(sentences) and len(excerpt) + len(sentences[offset + 1]) < 300:
                excerpt += " " + sentences[offset + 1]
            if len(excerpt) > 330:
                excerpt = excerpt[:330].rsplit(" ", 1)[0] + "…"
            score = min(len(excerpt), 220) / 220 + min(len(_SUBSTANTIVE.findall(excerpt)), 4) * 0.35
            score += min(len(_KEY_RESULT.findall(excerpt)), 2) * 0.65
            if excerpt[0].isascii() and excerpt[0].islower():
                score -= 0.5
            if score > best_score:
                best = Excerpt(first.page, excerpt)
                best_score = score
    return best
