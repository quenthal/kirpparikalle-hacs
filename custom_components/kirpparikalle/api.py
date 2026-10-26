"""Async client for the Kirppari-Kalle web UI.

Uses the same calls as the service's own login page. The password travels in
the query string (the site's own way), so request URLs and the original
exceptions are never logged or chained.
"""

from __future__ import annotations

from dataclasses import dataclass
import json

import aiohttp

from .const import BASE_URL, REQUEST_TIMEOUT
from .parsers import PageDoc, is_login_page

# A single-shop account is logged straight in without a shop list.
DEFAULT_COMPANY_ID = "default"


class KirppariKalleError(Exception):
    """Base error."""


class CannotConnect(KirppariKalleError):
    """The service could not be reached."""


class InvalidAuth(KirppariKalleError):
    """The username or password was rejected."""


class AuthExpired(KirppariKalleError):
    """The session is no longer logged in."""


class LoginFailed(KirppariKalleError):
    """Login did not succeed for another reason."""


@dataclass(frozen=True)
class Shop:
    """A flea market the account is linked to."""

    company_id: str
    name: str


class KirppariKalleApi:
    """Kirppari-Kalle over HTTP; the session keeps the login cookie."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def close(self) -> None:
        await self._session.close()

    async def _get(self, path: str, params: dict | None = None) -> tuple[str, str]:
        try:
            async with self._session.get(
                BASE_URL + path,
                params=params,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                resp.raise_for_status()
                return str(resp.url), await resp.text(errors="replace")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(type(err).__name__) from None

    async def _rpc(self, params: dict) -> dict:
        _, body = await self._get("rpc.php", {"request": "json_login", "lang": "fi", **params})
        try:
            data = json.loads(body)
        except ValueError:
            raise LoginFailed("rpc.php did not return JSON") from None
        if not isinstance(data, dict):
            raise LoginFailed("unexpected rpc.php response")
        return data

    async def page(self, name: str) -> PageDoc:
        """Fetch index.php?page=<name>; raises AuthExpired if logged out."""
        final_url, body = await self._get("index.php", {"page": name})
        doc = PageDoc(body)
        if is_login_page(final_url, doc.text):
            raise AuthExpired
        return doc

    async def _username_login(self, username: str, password: str) -> list[Shop]:
        """First login step. Empty list: logged straight in (one shop)."""
        self._session.cookie_jar.clear()
        await self._get("guest.php", {"page": "login"})
        data = await self._rpc(
            {
                "method": "username_login",
                "company_id": 1,
                "username": username,
                "password": password,
            }
        )

        if data.get("status") != "success":
            if data.get("object") == "username_or_password":
                raise InvalidAuth
            raise LoginFailed(f"login rejected ({data.get('object') or 'unknown'})")

        if str(data.get("redirect")).lower() == "true":
            return []

        companies = data.get("companies") or {}
        items = list(companies.values()) if isinstance(companies, dict) else list(companies)
        shops = [
            Shop(str(item["company_id"]), str(item.get("name", "")).strip())
            for item in items
            if isinstance(item, dict) and "company_id" in item
        ]
        if not shops:
            raise LoginFailed("no flea markets linked to the account")
        return shops

    async def _choose_company(self, company_id: str) -> None:
        data = await self._rpc({"method": "choose_company", "company_id": company_id})
        if data.get("status") != "success":
            raise LoginFailed("choosing the flea market was rejected")

    async def discover_shops(self, username: str, password: str) -> list[Shop]:
        """Log in and list the account's flea markets (for the config flow)."""
        shops = await self._username_login(username, password)
        if shops:
            return shops
        company = await self.page("companydetails")
        name = next((h for h in company.h1 if h), "Kirppari-Kalle")
        return [Shop(DEFAULT_COMPANY_ID, name)]

    async def login(self, username: str, password: str, company_id: str) -> None:
        """Log in to the given flea market and verify the session."""
        shops = await self._username_login(username, password)
        if shops:
            if company_id not in {shop.company_id for shop in shops}:
                raise LoginFailed("the flea market is no longer linked to the account")
            # The session cookie changes here once.
            await self._choose_company(company_id)
        await self.page("myreservations")
