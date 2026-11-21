import importlib.util
import tempfile
import unittest
from pathlib import Path

from research_agent.rag.documents import Chunk, chunk_text, load_corpus
from research_agent.rag.index import KnowledgeBase


class DocumentTests(unittest.TestCase):
    def test_chunks_keep_line_and_page_locations(self):
        self.assertEqual(chunk_text("  first \n\n  second  ", "a.txt"),
                         [Chunk("a.txt", "lines 1–3", "first\n\nsecond")])
        chunks = chunk_text("abcdef" * 250, "a.pdf", page=2)
        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(len(chunk.text) <= 600 and chunk.location == "p. 2" for chunk in chunks))

    def test_bad_text_does_not_discard_good_documents(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            (root / "bad.txt").write_bytes(b"\xff")
            (root / "good.md").write_text("中文资料", encoding="utf-8-sig")
            corpus = load_corpus(root)
        self.assertEqual(corpus.chunks, (Chunk("good.md", "lines 1–1", "中文资料"),))
        self.assertIn("bad.txt", corpus.issues[0])

    @unittest.skipUnless(importlib.util.find_spec("pymupdf"), "RAG extra is missing")
    def test_real_pdf_text_extraction_preserves_page(self):
        import pymupdf

        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            with pymupdf.open() as pdf:
                pdf.new_page().insert_text((40, 40), "SQLite journal")
                pdf.new_page().insert_text((40, 40), "Checkpoint copies WAL frames")
                pdf.save(root / "notes.pdf")
            corpus = load_corpus(root)
        self.assertEqual(corpus.issues, ())
        self.assertEqual([(chunk.location, chunk.text) for chunk in corpus.chunks],
                         [("p. 1", "SQLite journal"), ("p. 2", "Checkpoint copies WAL frames")])


class DemoEmbedder:
    def embed(self, texts):
        return [[3.0, 0.1] if "WAL" in text else [0.1, 2.0] for text in texts]


@unittest.skipUnless(importlib.util.find_spec("faiss"), "RAG extra is missing")
class RetrievalTests(unittest.TestCase):
    def test_cosine_rank_and_limit(self):
        wal = Chunk("wal.md", "lines 1–1", "WAL checkpoint")
        csv = Chunk("csv.txt", "lines 1–1", "CSV separator")
        kb = KnowledgeBase((csv, wal), DemoEmbedder())
        best, = kb.retrieve("WAL recovery", limit=1)
        self.assertEqual(best.chunk, wal)
        self.assertAlmostEqual(best.score, 1.0, places=5)

    def test_rejects_zero_vectors(self):
        class ZeroEmbedder:
            def embed(self, texts):
                return [[0, 0] for _ in texts]

        with self.assertRaisesRegex(ValueError, "norms"):
            KnowledgeBase((Chunk("a.txt", "lines 1–1", "text"),), ZeroEmbedder())
