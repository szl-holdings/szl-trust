import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.validate_json_strict import main, parse_json


@pytest.mark.parametrize(
    "document",
    [
        '{"outer":{"mode":"deny","mode":"allow"}}',
        '{"value":NaN}',
        '{"value":Infinity}',
        '{"value":-Infinity}',
        '{"value":1e999}',
    ],
)
def test_parse_json_rejects_ambiguous_documents(document: str) -> None:
    with pytest.raises(ValueError):
        parse_json(document)


def test_parse_json_accepts_finite_numbers() -> None:
    assert parse_json('{"value":1.5,"exponent":1e2}') == {
        "value": 1.5,
        "exponent": 100.0,
    }


def test_main_reports_invalid_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "valid.json").write_text('{"ok":true}\n', encoding="utf-8")
    (tmp_path / "invalid.json").write_text('{"value":NaN}\n', encoding="utf-8")

    assert main(["--root", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert f"INVALID {tmp_path / 'invalid.json'}" in captured.err
    assert "failures=1" in captured.out


def test_main_accepts_valid_tree(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "valid.json").write_text('{"ok":true}\n', encoding="utf-8")

    assert main(["--root", str(tmp_path)]) == 0
    assert "Validated 1 JSON files; failures=0." in capsys.readouterr().out
