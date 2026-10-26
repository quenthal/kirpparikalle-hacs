"""Config flow for Kirppari-Kalle."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .api import CannotConnect, InvalidAuth, KirppariKalleApi, LoginFailed, Shop
from .const import CONF_COMPANY_ID, CONF_SHOP_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


class KirppariKalleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Username + password, then pick the flea market."""

    VERSION = 1

    def __init__(self) -> None:
        self._username = ""
        self._password = ""
        self._shops: list[Shop] = []

    async def _with_api(self, func) -> Any:
        """Run func(api) with a throwaway session."""
        session = async_create_clientsession(
            self.hass, auto_cleanup=False, cookie_jar=aiohttp.CookieJar()
        )
        try:
            return await func(KirppariKalleApi(session))
        finally:
            await session.close()

    async def _try(self, func) -> tuple[Any, str | None]:
        try:
            return await self._with_api(func), None
        except InvalidAuth:
            return None, "invalid_auth"
        except CannotConnect:
            return None, "cannot_connect"
        except LoginFailed as err:
            _LOGGER.warning("Kirppari-Kalle login failed: %s", err)
            return None, "unknown"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            shops, error = await self._try(lambda api: api.discover_shops(username, password))
            if error:
                errors["base"] = error
            else:
                self._username, self._password, self._shops = username, password, shops
                if len(shops) == 1:
                    return await self._create(shops[0])
                return await self.async_step_shop()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
                }
            ),
            errors=errors,
        )

    async def async_step_shop(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            shop = next(s for s in self._shops if s.company_id == user_input[CONF_COMPANY_ID])
            return await self._create(shop)

        return self.async_show_form(
            step_id="shop",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_COMPANY_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=s.company_id, label=s.name)
                                for s in self._shops
                            ]
                        )
                    )
                }
            ),
        )

    async def _create(self, shop: Shop) -> ConfigFlowResult:
        await self.async_set_unique_id(f"{self._username.lower()}:{shop.company_id}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=shop.name,
            data={
                CONF_USERNAME: self._username,
                CONF_PASSWORD: self._password,
                CONF_COMPANY_ID: shop.company_id,
                CONF_SHOP_NAME: shop.name,
            },
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            _, error = await self._try(
                lambda api: api.login(
                    entry.data[CONF_USERNAME], password, entry.data[CONF_COMPANY_ID]
                )
            )
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: password}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR}),
            description_placeholders={"username": entry.data[CONF_USERNAME]},
            errors=errors,
        )
