"""Offline tests for Link pagination. No network and no tokens."""
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "estate_inventory",
    ROOT / "tools" / "estate_inventory.py",
)
inventory = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(inventory)


ORG_NEXT = (
    '<https://api.github.com/organizations/273360816/repos?type=all&per_page=100&page=2>;'
    ' rel="next"'
)


def _repo(number):
    return {
        "name": f"public-{number}",
        "full_name": f"szl-holdings/public-{number}",
        "default_branch": "main",
        "archived": False,
        "private": False,
        "updated_at": "2026-10-09T00:00:00Z",
    }


class LinkPaginationTests(unittest.TestCase):
    def test_module_does_not_name_the_refused_domain(self) -> None:
        source = (ROOT / "tools" / "estate_inventory.py").read_text(encoding="utf-8")
        self.assertNotIn("a11oy.com", source)
        self.assertIn("a-11-oy.com", source)
        self.assertIn("a11oy.net", source)

    def test_github_org_rewrite_is_followed_and_counted(self) -> None:
        calls = []

        def fetch(url, token=None):
            calls.append(url)
            if len(calls) == 1:
                return [_repo(i) for i in range(100)], {"Link": ORG_NEXT}, None
            return [_repo(i) for i in range(100, 141)], {"Link": None}, None

        rows, err = inventory.pages(
            "https://api.github.com/orgs/szl-holdings/repos?type=all&per_page=100",
            "token-must-not-leak",
            fetch=fetch,
            allowed_netloc=inventory.GITHUB_API,
            allow_org_rewrite=True,
        )
        self.assertIsNone(err)
        self.assertEqual(len(rows), 141)
        self.assertEqual(len(calls), 2)
        self.assertNotIn("page=2", calls[0])
        self.assertIn("/organizations/273360816/repos", calls[1])

    def test_full_page_without_next_is_not_complete(self) -> None:
        def fetch(url, token=None):
            return [_repo(i) for i in range(100)], {}, None

        rows, err = inventory.pages(
            "https://api.github.com/orgs/szl-holdings/repos?type=all&per_page=100",
            None,
            fetch=fetch,
            allowed_netloc=inventory.GITHUB_API,
            allow_org_rewrite=True,
        )
        self.assertEqual(len(rows), 100)
        self.assertEqual(err["type"], "FullPageWithoutNext")

    def test_foreign_next_host_is_rejected_before_another_fetch(self) -> None:
        calls = []

        def fetch(url, token=None):
            calls.append(url)
            return (
                [_repo(1)],
                {"Link": '<https://evil.example/repos>; rel="next"'},
                None,
            )

        _rows, err = inventory.pages(
            "https://api.github.com/orgs/szl-holdings/repos?type=all&per_page=100",
            "token-must-not-leak",
            fetch=fetch,
            allowed_netloc=inventory.GITHUB_API,
            allow_org_rewrite=True,
        )
        self.assertEqual(err["type"], "PaginationOriginChanged")
        self.assertEqual(len(calls), 1)

    def test_collect_stays_incomplete_when_github_pagination_fails(self) -> None:
        def fetch(url, token=None):
            if "api.github.com" in url:
                return [_repo(i) for i in range(100)], {}, None
            return [{"id": "SZLHOLDINGS/example", "private": False}], {}, None

        heads = []

        def head(url):
            heads.append(url)
            return 200, None

        data = inventory.collect(fetch=fetch, head=head)
        self.assertFalse(data["complete"])
        self.assertEqual(len(data["github"]["repositories"]), 100)
        self.assertIn("github.repositories", [item["scope"] for item in data["errors"]])
        self.assertEqual(heads, ["https://a-11-oy.com/", "https://a11oy.net/"])
        self.assertNotIn("a11oy.com", " ".join(heads))

    def test_missing_tokens_are_not_a_complete_catalog(self) -> None:
        def fetch(url, token=None):
            if "api.github.com" in url:
                return [_repo(1)], {}, None
            return [{"id": "SZLHOLDINGS/example", "private": False}], {}, None

        data = inventory.collect(fetch=fetch, head=lambda url: (200, None))
        self.assertFalse(data["complete"])
        self.assertIn("TokenAbsent", [item["type"] for item in data["errors"]])


if __name__ == "__main__":
    unittest.main()
