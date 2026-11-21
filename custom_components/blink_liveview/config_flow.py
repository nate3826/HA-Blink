"""Config flow for Blink Live View."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import BLINK_DOMAIN, DOMAIN


class BlinkLiveViewConfigFlow(ConfigFlow, domain=DOMAIN):
    """One-click setup; reuses the login of the core Blink integration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm setup."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if not self.hass.config_entries.async_entries(BLINK_DOMAIN):
            return self.async_abort(reason="no_blink")
        if user_input is not None:
            return self.async_create_entry(title="Blink Live View", data={})
        return self.async_show_form(step_id="user")
