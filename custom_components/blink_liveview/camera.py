"""Live-streaming camera entities for Blink cameras."""

from __future__ import annotations

from typing import Any

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BlinkLiveViewConfigEntry
from .const import BLINK_DOMAIN
from .relay import LiveViewRelay


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BlinkLiveViewConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add one live view camera per Blink camera."""
    async_add_entities(
        BlinkLiveViewCamera(name, relay) for name, relay in entry.runtime_data.values()
    )


class BlinkLiveViewCamera(Camera):
    """A Blink camera that streams live video."""

    _attr_has_entity_name = True
    _attr_name = "Live view"
    _attr_brand = "Blink"
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, camera_name: str, relay: LiveViewRelay) -> None:
        """Initialize the entity."""
        super().__init__()
        self._relay = relay
        self._attr_unique_id = f"{relay.serial}-liveview"
        # Attach to the device the core Blink integration already created.
        self._attr_device_info = DeviceInfo(
            identifiers={(BLINK_DOMAIN, relay.serial)}, name=camera_name
        )

    @property
    def is_streaming(self) -> bool:
        """Return True while Blink is sending live video."""
        return self._relay.streaming

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the relay address for use in other tools."""
        return {"stream_source": self._relay.url}

    async def stream_source(self) -> str | None:
        """Return the local relay; connecting to it starts the live view."""
        return self._relay.url

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return the latest Blink thumbnail (doesn't wake the camera)."""
        camera = self._relay.get_camera()
        return camera.image_from_cache if camera is not None else None
