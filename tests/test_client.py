from pathlib import Path

import httpx
import pytest
import respx

from finfacts.sec import client as client_mod
from finfacts.sec.client import SecClient

UA = "FinFacts-test/0.1 test@example.com"
URL = "https://data.sec.gov/submissions/CIK0000320193.json"


@pytest.fixture(autouse=True)
def _no_backoff_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    # tenacity sleeps via time.sleep inside its retrying object; make retries instant.
    for fn in (SecClient.get_json, SecClient.download, SecClient.last_modified_date):
        monkeypatch.setattr(fn.retry, "sleep", lambda _s: None)


@respx.mock
def test_sends_user_agent_and_parses_json() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, json={"cik": "320193"}))
    with SecClient(UA) as c:
        assert c.get_json(URL) == {"cik": "320193"}
    assert route.calls.last.request.headers["User-Agent"] == UA


@respx.mock
@pytest.mark.parametrize("status", sorted(client_mod.RETRYABLE_STATUS))
def test_retries_retryable_status(status: int) -> None:
    respx.get(URL).mock(side_effect=[httpx.Response(status), httpx.Response(200, json={})])
    with SecClient(UA) as c:
        assert c.get_json(URL) == {}


@respx.mock
def test_does_not_retry_404() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(404))
    with SecClient(UA) as c, pytest.raises(httpx.HTTPStatusError):
        c.get_json(URL)
    assert route.call_count == 1


@respx.mock
def test_gives_up_after_max_attempts() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(503))
    with SecClient(UA) as c, pytest.raises(httpx.HTTPStatusError):
        c.get_json(URL)
    assert route.call_count == 6


@respx.mock
def test_last_modified_date() -> None:
    respx.head(URL).mock(
        return_value=httpx.Response(200, headers={"Last-Modified": "Tue, 20 Oct 2026 04:52:50 GMT"})
    )
    with SecClient(UA) as c:
        assert c.last_modified_date(URL) == "2026-10-20"


@respx.mock
def test_download_is_atomic_and_cached(tmp_path: Path) -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, content=b"zipbytes"))
    dest = tmp_path / "x.zip"
    with SecClient(UA) as c:
        c.download(URL, dest)
        c.download(URL, dest)
    assert dest.read_bytes() == b"zipbytes"
    assert route.call_count == 1
    assert not list(tmp_path.glob("*.part"))
