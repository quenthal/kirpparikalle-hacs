"""Shared fixtures. All data is invented."""

from __future__ import annotations

import pytest

from custom_components.kirpparikalle.parsers import PageDoc

RESERVATIONS_HTML = """
<a>Kirjaudu ulos</a>
<table><tr><td>La 03.10.2026</td><td>-</td><td>La 10.10.2026</td></tr></table>
"""

COMPANY_HTML = """
<a>Kirjaudu ulos</a>
<h1>Esimerkkikirppis</h1>
<div>Maanantai: suljettu</div>
<div>Tiistai - Perjantai: 10-18</div>
<div>Lauantai - Sunnuntai: 10-16</div>
"""


def sales_html(rows: list[tuple[int, str, str]], balance: str) -> str:
    """mysales page in the real page's shape (hidden balance, detail columns)."""
    body = "".join(
        f"<tr><td>{n}</td><td>{name}</td><td>{price} €</td><td>1</td><td>0 %</td></tr>"
        for n, name, price in rows
    )
    return f"""
<a>Kirjaudu ulos</a>
<h1 id="top_page_title">Myynnin seuranta</h1>
<h2>Saldo</h2><div id="client_balance_container">&nbsp;</div>
<input type="hidden" id="client_balance_float" value="{balance}"/>
<div>Tiedot p&auml;ivitetty: 03.10.2026 11:55</div>
<table>
<tr><th>Nro</th><th>Nimi</th><th>Hinta</th>
<th class="detail_view">M&auml;&auml;r&auml;</th><th class="detail_view">ALV</th></tr>
<tr><td colspan="5">03.10.2026</td></tr>
{body}
</table>
"""


SALES_ROWS = [(55, "Talvisaappaat, 30", "8,00"), (7, "Housut, 122", "3,00")]


class FakeApi:
    """Stands in for KirppariKalleApi: serves fixture pages."""

    def __init__(self) -> None:
        self.logged_in = False
        self.sales_rows = list(SALES_ROWS)
        self.balance = "11.00"
        self.calls: list[str] = []
        self.login_error: Exception | None = None

    async def page(self, name: str) -> PageDoc:
        from custom_components.kirpparikalle.api import AuthExpired

        self.calls.append(name)
        if not self.logged_in:
            raise AuthExpired
        html = {
            "myreservations": RESERVATIONS_HTML,
            "companydetails": COMPANY_HTML,
            "mysales": sales_html(self.sales_rows, self.balance),
        }[name]
        return PageDoc(html)

    async def login(self, username: str, password: str, company_id: str) -> None:
        self.calls.append("login")
        if self.login_error:
            raise self.login_error
        self.logged_in = True

    async def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/ in every test."""
    return
