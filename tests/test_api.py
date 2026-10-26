"""HTTP client against a fake Kirppari-Kalle."""

from __future__ import annotations

import json
from urllib.parse import urlparse

import pytest

from custom_components.kirpparikalle.api import (
    AuthExpired,
    InvalidAuth,
    KirppariKalleApi,
    LoginFailed,
    Shop,
)


class FakeResponse:
    def __init__(self, url: str, body: str) -> None:
        self.url, self.body = url, body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self) -> None:
        pass

    async def text(self, errors: str = "strict") -> str:
        return self.body


class FakeSession:
    """The login endpoints as seen with a real account (values invented)."""

    def __init__(self, shops: list[str], password: str = "secret") -> None:
        self.shops, self.password = shops, password
        self.logged_in = False
        self.chosen: str | None = None
        self.cookie_jar = type("Jar", (), {"clear": lambda self: None})()

    def get(self, url, params=None, timeout=None):
        q = {k: str(v) for k, v in (params or {}).items()}
        path = urlparse(url).path
        base = "https://example.invalid/sovellus/"
        if path.endswith("guest.php"):
            return FakeResponse(url, "Kirjaudu sisään")
        if path.endswith("rpc.php"):
            if q["method"] == "username_login":
                if q["password"] != self.password:
                    return FakeResponse(
                        url, json.dumps({"status": "error", "object": "username_or_password"})
                    )
                if len(self.shops) == 1:
                    self.logged_in = True
                    return FakeResponse(url, json.dumps({"status": "success", "redirect": "true"}))
                companies = {
                    str(i): {"company_id": 100 + i, "name": n} for i, n in enumerate(self.shops)
                }
                return FakeResponse(
                    url,
                    json.dumps({"status": "success", "redirect": False, "companies": companies}),
                )
            if q["method"] == "choose_company":
                self.chosen = q["company_id"]
                self.logged_in = True
                return FakeResponse(url, json.dumps({"status": "success", "redirect": "true"}))
        if path.endswith("index.php"):
            if not self.logged_in:
                return FakeResponse(base + "guest.php?page=login", "Kirjaudu sisään")
            return FakeResponse(url, "<a>Kirjaudu ulos</a><h1>Ainoa kirppis</h1>")
        raise AssertionError(url)

    async def close(self):
        pass


async def test_discover_several_shops():
    api = KirppariKalleApi(FakeSession(["Kirppis A", "Kirppis B"]))
    shops = await api.discover_shops("user", "secret")
    assert shops == [Shop("100", "Kirppis A"), Shop("101", "Kirppis B")]


async def test_discover_single_shop_reads_name():
    api = KirppariKalleApi(FakeSession(["Ainoa"]))
    assert await api.discover_shops("user", "secret") == [Shop("default", "Ainoa kirppis")]


async def test_login_chooses_company():
    session = FakeSession(["Kirppis A", "Kirppis B"])
    await KirppariKalleApi(session).login("user", "secret", "101")
    assert session.chosen == "101"


async def test_wrong_password():
    with pytest.raises(InvalidAuth) as err:
        await KirppariKalleApi(FakeSession(["A"])).login("user", "wrong", "default")
    assert "wrong" not in str(err.value)


async def test_shop_no_longer_linked():
    with pytest.raises(LoginFailed):
        await KirppariKalleApi(FakeSession(["A", "B"])).login("user", "secret", "999")


async def test_logged_out_page():
    with pytest.raises(AuthExpired):
        await KirppariKalleApi(FakeSession(["A"])).page("mysales")
