"""Runtime patch for pyalarmdotcomajax==0.5.13 websocket bugs (homelab fork).

pyalarmdotcomajax is a pip dependency that HA installs into site-packages, so its
files can't be edited or bind-mounted (HA's installer fails on a mounted file and
then treats the whole package as missing). This module patches the installed
package's objects in memory instead. base_device.py imports it and calls apply()
at load time; apply() is idempotent.

THE TWO BUGS FIXED (source reference: pyalarmdotcomajax==0.5.13, upstream tag
v0.5.13 -- neither reported upstream as of 2026-08-12):

1. pyalarmdotcomajax/websockets/messages.py's process_raw_message() left `device`
   unbound when device_registry.get() raised UnkonwnDevice (pyalarmdotcomajax's own
   term for devices on its internal blacklist), causing UnboundLocalError on every
   websocket event for such a device -- ~18x/day on cerebro, each one tearing down
   and reconnecting the websocket (controller.py's
   CONF_DEFAULT_WEBSOCKET_RECONNECT_TIMEOUT = 300s gap per occurrence). Now raises
   UnsupportedWebSocketMessage instead, which the patched _connect() below catches
   and skips per-message instead of killing the connection.

2. pyalarmdotcomajax/websockets/client.py's WebSocketClient._connect() didn't
   catch-all on the token-fetch call -- only (UnexpectedResponse, AuthenticationFailed)
   were caught there. Any other exception (observed: RuntimeError: Session is closed,
   when the aiohttp session is torn down mid-request during a reload/restart) escaped
   uncaught from the fire-and-forget task created in start(), never transitioning
   `state` to DISCONNECTED -- which left the HA-side controller.py reconnect monitor's
   `_ws_close_event.wait()` stuck forever for that instance, no automatic recovery
   short of a full HA restart. Now degrades cleanly to DISCONNECTED like every other
   failure path in that method.
"""

from __future__ import annotations

import json
import logging

import aiohttp

from pyalarmdotcomajax.exceptions import (
    AuthenticationFailed,
    UnexpectedResponse,
    UnkonwnDevice,
    UnsupportedWebSocketMessage,
)
from pyalarmdotcomajax.websockets import client as _ws_client
from pyalarmdotcomajax.websockets import messages as _ws_messages
from pyalarmdotcomajax.websockets.client import WebSocketState

# Log under the original modules' own logger names, not this module's -- so
# anyone with existing debug-logging config for pyalarmdotcomajax.websockets.*
# (e.g. via HA's logger: integration) keeps seeing these lines in the same
# place they would from the unpatched code.
_messages_log = logging.getLogger("pyalarmdotcomajax.websockets.messages")
_client_log = logging.getLogger("pyalarmdotcomajax.websockets.client")
log = logging.getLogger(__name__)

_PATCH_MARKER = "_homelab_ws_patched"


def _patched_process_raw_message(message, device_registry):
    """pyalarmdotcomajax.websockets.messages.process_raw_message, patched.

    Identical to upstream 0.5.13 except: UnkonwnDevice now raises
    UnsupportedWebSocketMessage instead of falling through with `device` left
    unbound (the original UnboundLocalError bug).
    """

    try:
        device = device_registry.get(f"{message['UnitId']}-{message['DeviceId']}")
    except UnkonwnDevice:
        # This tends to happen for devices on pyalarmdotcomajax's blacklist.
        _messages_log.debug(
            "Got a message for unknown device"
            f" {message['UnitId']}-{message['DeviceId']}:\n{json.dumps(message, indent=4)}"
        )
        raise UnsupportedWebSocketMessage(message) from None

    try:
        if {"FenceId", "IsInsideNow"} <= set(message.keys()):
            # Geofence Event (Not Yet Supported)
            pass
        elif {"EventType", "EventValue", "QstringForExtraData"} <= set(message.keys()):
            _messages_log.debug("WebSocket Message Type: Event")
            return _ws_messages.EventMessage(message, device)
        elif {"EventType", "CorrelatedId"} <= set(message.keys()):
            _messages_log.debug("WebSocket Message Type: Monitoring Event")
            return _ws_messages.MonitoringEventMessage(message, device)
        elif {"Property", "PropertyValue"} <= set(message.keys()):
            _messages_log.debug("WebSocket Message Type: Property Change")
            return _ws_messages.PropertyChangeMessage(message, device)
        elif {"NewState", "FlagMask"} <= set(message.keys()):
            _messages_log.debug("WebSocket Message Type: State Change")
            return _ws_messages.StatusChangeMessage(message, device)
    except KeyError:
        _messages_log.exception(f"Failed to parse websocket message: {message}")

    raise UnsupportedWebSocketMessage(message)


async def _patched_connect(self) -> None:
    """WebSocketClient._connect, patched.

    Identical to upstream 0.5.13 except: (1) the token-fetch call now has a
    catch-all `except Exception` so any failure there properly transitions
    `state` to DISCONNECTED instead of dying as an orphaned, never-retried task;
    (2) the per-message handler also catches UnsupportedWebSocketMessage (raised
    by _patched_process_raw_message above) and skips it instead of tearing down
    the whole connection.
    """

    try:
        self._ws_auth_token = await self._async_get_websocket_token()
    except (UnexpectedResponse, AuthenticationFailed) as err:
        raise AuthenticationFailed from err
    except Exception:
        if self.state != WebSocketState.STOPPED:
            _client_log.exception("Unexpected error fetching WebSocket auth token")
            self.state = WebSocketState.DISCONNECTED
        return

    if not self._ws_auth_token:
        raise AuthenticationFailed("async_connect(): Failed to get WebSocket authentication token.")

    try:
        async with self._websession.ws_connect(
            self.WEBSOCKET_ENDPOINT_TEMPLATE.format(self._ws_auth_token),
            headers=self._ajax_headers,
            timeout=30,
        ) as websocket:
            self.state = WebSocketState.RUNNING

            async for msg in websocket:
                if self.state == WebSocketState.STOPPED:
                    break

                # Message is JSON but encoded as text.
                if msg.type != aiohttp.WSMsgType.TEXT:
                    pass
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    _client_log.warning("AIOHTTP websocket connection closed")
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    _client_log.exception("AIOHTTP websocket error: '%s'", msg.data)
                    break

                try:
                    await self._async_handle_message(json.loads(msg.data))
                except (TypeError, ValueError):
                    _client_log.warning("Unable to parse message from Alarm.com: %s", msg.data)
                    # TODO: On failure, refresh everything synchronous HTTP endpoints.
                except UnsupportedWebSocketMessage:
                    _client_log.debug("Ignoring unsupported/unknown-device websocket message: %s", msg.data)

    except aiohttp.ClientConnectorError:
        if self.state != WebSocketState.STOPPED:
            _client_log.exception("WebSocket client connection error")
            self.state = WebSocketState.DISCONNECTED

    except Exception:
        if self.state != WebSocketState.STOPPED:
            _client_log.exception("Unexpected WebSocket error")
            self.state = WebSocketState.DISCONNECTED

    else:
        if self.state != WebSocketState.STOPPED:
            self.state = WebSocketState.DISCONNECTED


def apply() -> None:
    """Idempotently monkeypatch the installed pyalarmdotcomajax==0.5.13 package."""

    if getattr(_ws_client, _PATCH_MARKER, False):
        return

    _ws_messages.process_raw_message = _patched_process_raw_message
    # client.py imported process_raw_message by name at its own module load time
    # (`from pyalarmdotcomajax.websockets.messages import ... process_raw_message`)
    # -- patching the source module's attribute alone doesn't affect that already-
    # bound reference in client.py's namespace, so it has to be patched here too.
    _ws_client.process_raw_message = _patched_process_raw_message
    _ws_client.WebSocketClient._connect = _patched_connect

    setattr(_ws_client, _PATCH_MARKER, True)
    log.info("Applied homelab pyalarmdotcomajax websocket patches")
