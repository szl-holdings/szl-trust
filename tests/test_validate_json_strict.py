import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.validate_json_strict import main, parse_json


class StrictJsonTests(unittest.TestCase):
    def test_parse_json_rejects_ambiguous_documents(self) -> None:
        documents = (
            '{"outer":{"mode":"deny","mode":"allow"}}',
            '{"value":NaN}',
            '{"value":Infinity}',
            '{"value":-Infinity}',
            '{"value":1e999}',
        )
        for document in documents:
            with self.subTest(document=document):
                with self.assertRaises(ValueError):
                    parse_json(document)

    def test_parse_json_accepts_finite_numbers(self) -> None:
        self.assertEqual(
            parse_json('{"value":1.5,"exponent":1e2}'),
            {"value": 1.5, "exponent": 100.0},
        )

    def test_main_reports_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "valid.json").write_text('{"ok":true}\n', encoding="utf-8")
            (root / "invalid.json").write_text('{"value":NaN}\n', encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = main(["--root", directory])
            self.assertEqual(result, 1)
            self.assertIn(f"INVALID {root / 'invalid.json'}", stderr.getvalue())
            self.assertIn("failures=1", stdout.getvalue())

    def test_main_accepts_valid_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nested").mkdir()
            (root / "nested" / "valid.json").write_text(
                '{"ok":true}\n', encoding="utf-8"
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = main(["--root", directory])
            self.assertEqual(result, 0)
            self.assertIn("Validated 1 JSON files; failures=0.", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
