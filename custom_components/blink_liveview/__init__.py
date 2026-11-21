"""Blink Live View: real live streams for Blink cameras in Home Assistant."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import BLINK_DOMAIN
from .relay import LiveViewRelay

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CAMERA]

type BlinkLiveViewConfigEntry = ConfigEntry[dict[str, tuple[str, LiveViewRelay]]]


def _blink_apis(hass: HomeAssistant) -> list[Any]:
    """Return the blinkpy ``Blink`` object of every loaded Blink config entry."""
    apis = []
    for entry in hass.config_entries.async_entries(BLINK_DOMAIN):
        if entry.state is not ConfigEntryState.LOADED:
            continue
        coordinator = getattr(entry, "runtime_data", None)
        blink = getattr(coordinator, "api", None)
        if blink is not None:
            apis.append(blink)
    return apis


def find_camera(hass: HomeAssistant, serial: str) -> Any | None:
    """Look up a blinkpy camera by serial number.

    Looked up on every connection, so that we pick up the new blinkpy objects
    after the Blink integration reloads (for example after re-authenticating).
    """
    for blink in _blink_apis(hass):
        for camera in blink.cameras.values():
            if camera.serial == serial:
                return camera
    return None


async def async_setup_entry(hass: HomeAssistant, entry: BlinkLiveViewConfigEntry) -> bool:
    """Start one relay per Blink camera."""
    apis = _blink_apis(hass)
    if not apis:
        raise ConfigEntryNotReady("The Blink integration is not loaded yet")

    relays: dict[str, tuple[str, LiveViewRelay]] = {}
    for blink in apis:
        for name, camera in blink.cameras.items():
            serial = camera.serial
            if serial in relays:
                continue
            relay = LiveViewRelay(serial, lambda s=serial: find_camera(hass, s))
            await relay.async_start()
            relays[serial] = (name, relay)

    async def _stop_relays() -> None:
        for _, relay in relays.values():
            await relay.async_stop()

    entry.async_on_unload(_stop_relays)
    entry.runtime_data = relays

    _LOGGER.debug("Blink Live View relays: %s", {s: r.url for s, (_, r) in relays.items()})
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BlinkLiveViewConfigEntry) -> bool:
    """Unload the integration."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
