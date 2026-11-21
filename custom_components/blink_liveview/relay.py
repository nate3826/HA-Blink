"""Local relay that turns a Blink live view into a plain MPEG-TS TCP stream.

Blink live view does not use RTSP. The liveview API returns an ``immis://``
address that speaks Blink's own IMMI protocol over TLS; the video inside it
is ordinary MPEG-TS. blinkpy knows that protocol (``BlinkLiveStream``), but
its built-in server shuts down for good when the last viewer leaves, so its
URL is only good once.

This relay keeps one TCP port open for each camera for as long as the
integration is loaded, so the camera entity always reports the same
``tcp://127.0.0.1:<port>`` stream source. Each time a viewer (Home Assistant's
stream worker or go2rtc) connects and no session is running, the relay starts
a new Blink live view session. When the last viewer leaves, it ends the
session so the camera can go back to sleep.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
import ssl
import time
from typing import Any

from blinkpy import api
from blinkpy.livestream import BlinkLiveStream

from .const import FAILURE_COOLDOWN, RELAY_HOST

_LOGGER = logging.getLogger(__name__)

IMMI_HEADER_LEN = 9
IMMI_MSG_VIDEO = 0x00
TS_SYNC_BYTE = 0x47


class LiveViewError(Exception):
    """Raised when Blink will not start a live view."""


class _RelayLiveStream(BlinkLiveStream):
    """BlinkLiveStream with a sturdier receive loop.

    The stock loop reads with ``StreamReader.read(n)``, which can return fewer
    than ``n`` bytes over TLS and then drops the session. Here we use
    ``readexactly``, and a viewer that breaks no longer stops the stream for
    the other viewers.
    """

    async def recv(self) -> None:
        reader = self.target_reader
        try:
            while True:
                header = await reader.readexactly(IMMI_HEADER_LEN)
                msgtype = header[0]
                length = int.from_bytes(header[5:9], byteorder="big")
                if length <= 0:
                    continue
                payload = await reader.readexactly(length)
                if msgtype != IMMI_MSG_VIDEO or payload[0] != TS_SYNC_BYTE:
                    continue
                for writer in list(self.clients):
                    if writer.is_closing():
                        continue
                    try:
                        writer.write(payload)
                        await writer.drain()
                    except (ConnectionError, RuntimeError):
                        _LOGGER.debug("Dropping a viewer whose connection broke")
                        writer.close()
        except asyncio.IncompleteReadError:
            _LOGGER.debug("Blink closed the live view connection")
        except ssl.SSLError as err:
            if err.reason != "APPLICATION_DATA_AFTER_CLOSE_NOTIFY":
                _LOGGER.warning("TLS error on Blink live view: %s", err)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Unexpected error while receiving Blink live view")
        finally:
            self.target_writer.close()


class LiveViewRelay:
    """A fixed local TCP endpoint for one Blink camera."""

    def __init__(self, serial: str, camera_getter: Callable[[], Any]) -> None:
        """Set up the relay. ``camera_getter`` returns the blinkpy camera or None."""
        self.serial = serial
        self._camera_getter = camera_getter
        self._server: asyncio.Server | None = None
        self._session: _RelayLiveStream | None = None
        self._session_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._last_failure = 0.0

    def get_camera(self) -> Any | None:
        """Return the blinkpy camera, or None if Blink no longer has it."""
        return self._camera_getter()

    @property
    def url(self) -> str | None:
        """Return the stream source URL, or None if the relay is not running."""
        if self._server is None or not self._server.sockets:
            return None
        host, port = self._server.sockets[0].getsockname()[:2]
        return f"tcp://{host}:{port}"

    @property
    def streaming(self) -> bool:
        """Return True while a Blink live view session is running."""
        return self._session_task is not None and not self._session_task.done()

    async def async_start(self) -> None:
        """Open the local listening socket."""
        self._server = await asyncio.start_server(self._handle_client, RELAY_HOST, 0)
        _LOGGER.debug("Relay for %s listening on %s", self.serial, self.url)

    async def async_stop(self) -> None:
        """Stop listening and end any running session."""
        if self._server is not None:
            self._server.close()
            self._server = None
        self._end_session()
        if self._session_task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._session_task), 10)
            except (TimeoutError, asyncio.TimeoutError):
                self._session_task.cancel()
            except Exception:  # noqa: BLE001 - shutting down regardless
                pass

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            session = await self._async_get_session()
        except Exception as err:  # noqa: BLE001 - logged, viewer is closed
            _LOGGER.warning("Could not start Blink live view for %s: %s", self.serial, err)
            writer.close()
            return

        session.clients.append(writer)
        _LOGGER.debug("Viewer joined %s (%d connected)", self.serial, len(session.clients))
        try:
            # Viewers don't send anything; wait for them to hang up.
            while not writer.is_closing():
                if not await reader.read(1024):
                    break
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            if writer in session.clients:
                session.clients.remove(writer)
            if not writer.is_closing():
                writer.close()
            _LOGGER.debug("Viewer left %s (%d connected)", self.serial, len(session.clients))
            if not session.clients and session is self._session:
                self._end_session()

    async def _async_get_session(self) -> _RelayLiveStream:
        async with self._lock:
            if self._session is not None and self.streaming:
                return self._session

            wait = FAILURE_COOLDOWN - (time.monotonic() - self._last_failure)
            if wait > 0:
                raise LiveViewError(f"last attempt failed, retrying in {wait:.0f}s")

            camera = self.get_camera()
            if camera is None:
                raise LiveViewError("camera not found in the Blink integration")

            try:
                response = await api.request_camera_liveview(
                    camera.sync.blink,
                    camera.sync.network_id,
                    camera.camera_id,
                    camera_type=camera.camera_type,
                )
            except Exception as err:
                self._last_failure = time.monotonic()
                raise LiveViewError(f"live view request failed: {err}") from err

            server = (response or {}).get("server", "") if isinstance(response, dict) else ""
            if not server.startswith("immis://"):
                self._last_failure = time.monotonic()
                detail = (response or {}).get("message") if isinstance(response, dict) else None
                raise LiveViewError(
                    detail or f"unexpected response from Blink: {response!r}"
                )

            session = _RelayLiveStream(camera, response)
            self._session = session
            self._session_task = asyncio.get_running_loop().create_task(
                self._run_session(session), name=f"blink_liveview_{self.serial}"
            )
            return session

    async def _run_session(self, session: _RelayLiveStream) -> None:
        _LOGGER.debug("Blink live view session started for %s", self.serial)
        try:
            await session.feed()
        except asyncio.CancelledError:
            session.stop()
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Blink live view for %s failed: %s", self.serial, err)
            self._last_failure = time.monotonic()
            session.stop()
        finally:
            _LOGGER.debug("Blink live view session ended for %s", self.serial)
            if self._session is session:
                self._session = None

    def _end_session(self) -> None:
        if self._session is not None:
            # Closing the Blink connection lets feed() wind down on its own,
            # which also tells the Blink API the command is done.
            self._session.stop()
