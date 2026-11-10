# SPDX-License-Identifier: Apache-2.0
"""Offline tests for the fail-closed forbidden-domain scanner."""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
import sys
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import check_forbidden_domain as checker


class ForbiddenDomainScannerTests(unittest.TestCase):
    def _scan_files(self, files: dict[str, bytes]) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for name, content in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                paths.append(path)
            with mock.patch.object(checker, "tracked_files", return_value=paths):
                return checker.scan(root)

    def test_clean_and_guarded_lines_pass(self) -> None:
        self.assertEqual(
            self._scan_files(
                {
                    "README.md": (
                        b"Use https://a-11-oy.com for the product.\n"
                        b"Never use a11oy.com in new references.\n"
                        b"assertNotIn('a11oy.com', text)\n"
                    )
                }
            ),
            [],
        )

    def test_unmentioned_domain_fails(self) -> None:
        violations = self._scan_files({"README.md": b"Visit https://a11oy" + b".com\n"})
        self.assertEqual(len(violations), 1)
        self.assertIn("README.md:1:Visit https://a11oy" + ".com", violations[0])

    def test_domain_in_path_does_not_exempt_content(self) -> None:
        self.assertEqual(
            self._scan_files({"a11oy" + ".com-not-a-rule.txt": b"ordinary content\n"}),
            [],
        )

    def test_git_failure_is_an_error(self) -> None:
        completed = mock.Mock(returncode=128, stdout=b"", stderr=b"not a repository")
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(checker.subprocess, "run", return_value=completed):
                with self.assertRaisesRegex(RuntimeError, "git ls-files failed"):
                    checker.tracked_files(Path(directory))

    def test_empty_git_tree_is_an_error(self) -> None:
        completed = mock.Mock(returncode=0, stdout=b"", stderr=b"")
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(checker.subprocess, "run", return_value=completed):
                with self.assertRaisesRegex(RuntimeError, "no files"):
                    checker.tracked_files(Path(directory))

    def test_invalid_utf8_path_is_an_error(self) -> None:
        completed = mock.Mock(returncode=0, stdout=b"bad\xff\0", stderr=b"")
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(checker.subprocess, "run", return_value=completed):
                with self.assertRaisesRegex(RuntimeError, "invalid UTF-8 filename"):
                    checker.tracked_files(Path(directory))

    def test_main_reports_failure_closed(self) -> None:
        with mock.patch.object(checker, "scan", side_effect=RuntimeError("scan unavailable")):
            output = io.StringIO()
            with contextlib.redirect_stderr(output):
                self.assertEqual(checker.main(["."]), 2)
            self.assertIn("scan unavailable", output.getvalue())


if __name__ == "__main__":
    unittest.main()
