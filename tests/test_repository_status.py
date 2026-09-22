from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RepositoryStatusTests(unittest.TestCase):
    def test_current_proof_source_ownership_is_unambiguous(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        history = (ROOT / "DEPRECATED.md").read_text(encoding="utf-8")

        self.assertIn("ACTIVE HISTORICAL PROOF REGISTRY", readme)
        self.assertIn("a11oy-net", readme)
        self.assertIn("archived mirror", readme)
        self.assertIn("Archived historical documentation mirror", readme)
        self.assertNotIn("DEPRECATED — migrated to", readme)

        self.assertIn("Historical consolidation note — superseded", history)
        self.assertIn("`szl-trust`", history)
        self.assertIn("`a11oy-net`", history)
        self.assertIn("`docs-site`", history)
        self.assertIn("archived historical documentation mirror", history)
        self.assertNotIn("Canonical published home", history)

    def test_contribution_terms_match_the_checked_in_license(self) -> None:
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")

        self.assertIn("Attribution 4.0 International", license_text)
        self.assertIn("CC-BY-4.0", contributing)
        self.assertIn("Contributing to szl-trust", contributing)
        self.assertNotIn("source-available, proprietary", contributing)
        self.assertNotIn("Contributing to ouroboros", contributing)


if __name__ == "__main__":
    unittest.main()
