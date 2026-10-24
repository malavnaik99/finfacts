import pytest

from finfacts.eval.run import _sql_from, score


@pytest.mark.parametrize(
    ("rows", "gold", "kind", "ok"),
    [
        ([(100.4,)], 100.0, "number", True),  # within 0.5%
        ([(101.0,)], 100.0, "number", False),
        ([(None,)], 100.0, "number", False),
        ([], 100.0, "number", False),
        ([(38.0,)], 38, "integer", True),
        ([("aapl",)], "AAPL", "ticker", True),
        ([("GOOG",)], "GOOGL;GOOG;GOOGM", "ticker", True),  # any of the company's tickers
        ([("MSFT",)], "AAPL", "ticker", False),
        ([("MSFT",), ("AAPL",)], ["AAPL", "MSFT"], "ticker_set", True),  # any order
        ([("MSFT",)], ["AAPL", "MSFT"], "ticker_set", False),
        ([(" financials ",)], "Financials", "text", True),
    ],
)
def test_score(rows: list[tuple[object, ...]], gold: object, kind: str, ok: bool) -> None:
    assert score(rows, gold, kind) is ok


def test_sql_from_code_block() -> None:
    assert _sql_from("Here:\n```sql\nselect 1;\n```") == "select 1"
    assert _sql_from("select 2") == "select 2"
