"""Seshat: retrieve image bytes in HA, publish native entities and events."""

import asyncio
import hashlib
import logging
from datetime import UTC, datetime

import voluptuous as vol
from homeassistant.components.image import async_get_image
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event

from .client import Client
from .const import DOMAIN, EVENT
from .worker import LatestWorker

LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR]


class Controller:
    def __init__(self, hass, entry):
        self.hass, self.entry = hass, entry
        self.source = entry.data["image_entity"]
        self.client = Client(async_get_clientsession(hass), entry.data["url"], entry.data["api_key"])
        self.worker = LatestWorker(self.process, entry.data["debounce_ms"] / 1000)
        self.result = None
        self.available = False
        self.last_hash = None
        self.force = False
        self.retry = None
        self.signal = f"{DOMAIN}_{entry.entry_id}"

    @callback
    def trigger(self, event=None, force=False):
        # Token rotation alone is not an image change. Other attributes count.
        if event is not None:
            old, new = event.data.get("old_state"), event.data.get("new_state")
            if old and new and old.state == new.state:
                ignored = {"access_token", "entity_picture"}
                before = {k: v for k, v in old.attributes.items() if k not in ignored}
                after = {k: v for k, v in new.attributes.items() if k not in ignored}
                # A changed entity_picture URL can contain a genuine image change.
                old_picture = str(old.attributes.get("entity_picture", "")).split("?token=", 1)[0]
                new_picture = str(new.attributes.get("entity_picture", "")).split("?token=", 1)[0]
                if before == after and old_picture == new_picture:
                    return
        self.force |= force
        if self.retry:
            self.retry.cancel()
            self.retry = None
        self.worker.trigger()

    async def process(self, generation):
        force, self.force = self.force, False
        try:
            state = self.hass.states.get(self.source)
            if state is None or state.state in ("unavailable", "unknown"):
                raise ValueError("Source image unavailable")
            image = await async_get_image(self.hass, self.source, timeout=15)
            if len(image.content) > 20 * 1024 * 1024:
                raise ValueError("Image exceeds integration safety limit")
            digest = await self.hass.async_add_executor_job(lambda: hashlib.sha256(image.content).hexdigest())
            if generation != self.worker.generation:
                return
            if digest == self.last_hash and self.available and not force:
                return
            result = await self.client.recognize(image.content, image.content_type)
            if generation != self.worker.generation:
                return  # Never publish a result superseded while inference ran.
            result.update(
                {
                    "source_entity": self.source,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "faces_detected": len(result["faces"]),
                }
            )
            best = result["best_match"]
            result.update(
                {
                    "person": best["person"] if best else "No Face",
                    "confidence": best["confidence"] if best else 0.0,
                    "distance": best["distance"] if best else None,
                    # Older add-ons remain usable while the two components are upgraded.
                    "gesture": result.get("gesture", "disabled"),
                    "gesture_quality": result.get("gesture_quality"),
                    "gesture_arm": result.get("gesture_arm"),
                    "gesture_reason": result.get("gesture_reason", "addon_does_not_report_gestures"),
                }
            )
            self.last_hash, self.result, self.available = digest, result, True
            async_dispatcher_send(self.hass, self.signal)
            self.hass.bus.async_fire(EVENT, result)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Isolate integration/network failures from HA; omit secrets and payloads.
            LOGGER.warning("Seshat recognition failed (%s); retry in 30s", type(error).__name__)
            self.available = False
            async_dispatcher_send(self.hass, self.signal)
            if not self.worker.event.is_set():
                self.retry = self.hass.loop.call_later(30, self.trigger)

    async def stop(self, _event=None):
        if self.retry:
            self.retry.cancel()
        await self.worker.stop()


async def async_setup_entry(hass, entry):
    controller = Controller(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = controller
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(async_track_state_change_event(hass, [controller.source], controller.trigger))
    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, controller.stop))
    controller.worker.start()
    controller.trigger()

    async def recognize_now(_call):
        controller.trigger(force=True)

    hass.services.async_register(DOMAIN, "recognize", recognize_now, schema=vol.Schema({}))
    return True


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await hass.data[DOMAIN].pop(entry.entry_id).stop()
        hass.services.async_remove(DOMAIN, "recognize")
        return True
    return False
