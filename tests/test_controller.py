"""Controller contracts using minimal HA doubles; not a live HAOS test."""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.fixture
async def controller(monkeypatch):
    modules = {
        name: types.ModuleType(name)
        for name in (
            "homeassistant",
            "homeassistant.components",
            "homeassistant.components.image",
            "homeassistant.const",
            "homeassistant.core",
            "homeassistant.helpers",
            "homeassistant.helpers.aiohttp_client",
            "homeassistant.helpers.dispatcher",
            "homeassistant.helpers.event",
        )
    }
    image = modules["homeassistant.components.image"]
    image.async_get_image = AsyncMock(
        return_value=types.SimpleNamespace(content=b"first", content_type="image/png")
    )
    modules["homeassistant.const"].EVENT_HOMEASSISTANT_STOP = "stop"
    modules["homeassistant.const"].Platform = types.SimpleNamespace(SENSOR="sensor")
    modules["homeassistant.core"].callback = lambda function: function
    modules["homeassistant.helpers.aiohttp_client"].async_get_clientsession = lambda hass: None
    modules["homeassistant.helpers.dispatcher"].async_dispatcher_send = Mock()
    modules["homeassistant.helpers.event"].async_track_state_change_event = Mock()
    for name, value in modules.items():
        monkeypatch.setitem(sys.modules, name, value)
    root = Path(__file__).parents[1] / "custom_components/seshat"
    spec = importlib.util.spec_from_file_location(
        "seshat_contract", root / "__init__.py", submodule_search_locations=[str(root)]
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "seshat_contract", module)
    spec.loader.exec_module(module)
    hass = types.SimpleNamespace(
        states=types.SimpleNamespace(get=lambda entity: types.SimpleNamespace(state="timestamp")),
        bus=types.SimpleNamespace(async_fire=Mock()),
        loop=asyncio.get_running_loop(),
        async_add_executor_job=AsyncMock(side_effect=lambda function: function()),
    )
    entry = types.SimpleNamespace(
        entry_id="test",
        data={
            "url": "http://local-seshat:8000",
            "api_key": "x" * 32,
            "image_entity": "image.front_door_event_image",
            "debounce_ms": 0,
        },
    )
    instance = module.Controller(hass, entry)
    instance.client.recognize = AsyncMock(return_value={"faces": [], "best_match": None, "processing_ms": 1})
    instance.test_image = image.async_get_image
    yield instance
    if instance.retry:
        instance.retry.cancel()
    for name in list(sys.modules):
        if name.startswith("seshat_contract."):
            monkeypatch.delitem(sys.modules, name)


async def test_duplicate_image_suppression_and_force(controller):
    await controller.process(0)
    await controller.process(0)
    assert controller.client.recognize.await_count == 1
    assert controller.result["person"] == "No Face"
    assert controller.hass.bus.async_fire.call_count == 1
    controller.force = True
    await controller.process(0)
    assert controller.client.recognize.await_count == 2


async def test_changed_image_processes(controller):
    await controller.process(0)
    controller.test_image.return_value.content = b"second"
    await controller.process(0)
    assert controller.client.recognize.await_count == 2


async def test_failure_is_unavailable_and_same_image_retries(controller):
    await controller.process(0)
    controller.force = True
    controller.client.recognize.side_effect = TimeoutError()
    await controller.process(0)
    assert not controller.available and controller.retry is not None
    assert controller.hass.bus.async_fire.call_count == 1
    controller.client.recognize.side_effect = None
    await controller.process(0)
    assert controller.available
    assert controller.hass.bus.async_fire.call_count == 2


async def test_stale_inference_is_not_published(controller):
    async def supersede(*_args):
        controller.worker.trigger()
        return {"faces": [], "best_match": None, "processing_ms": 1}

    controller.client.recognize.side_effect = supersede
    await controller.process(0)
    assert controller.result is None
    controller.hass.bus.async_fire.assert_not_called()


async def test_token_rotation_ignored_attribute_change_processed(controller):
    old = types.SimpleNamespace(
        state="same",
        attributes={"access_token": "a", "entity_picture": "/api/image_proxy/image.front?token=a"},
    )
    new = types.SimpleNamespace(
        state="same",
        attributes={"access_token": "b", "entity_picture": "/api/image_proxy/image.front?token=b"},
    )
    event = types.SimpleNamespace(data={"old_state": old, "new_state": new})
    controller.trigger(event)
    assert controller.worker.generation == 0
    new.attributes["event_id"] = "new"
    controller.trigger(event)
    assert controller.worker.generation == 1


async def test_unknown_is_distinct_from_no_face(controller):
    face = {"person": "Unknown", "confidence": 0, "distance": 0.9, "matched": False}
    controller.client.recognize.return_value = {"faces": [face], "best_match": face, "processing_ms": 5}
    await controller.process(0)
    assert controller.available and controller.result["person"] == "Unknown"
    assert controller.result["faces_detected"] == 1


async def test_unavailable_source_does_not_call_recognition(controller):
    controller.hass.states.get = lambda _: None
    await controller.process(0)
    assert not controller.available
    controller.client.recognize.assert_not_awaited()


async def test_gesture_and_identity_published_together(controller):
    face = {
        "person": "Saad",
        "confidence": 0.8,
        "distance": 0.2,
        "matched": True,
        "gesture": {"label": "pointing_up", "quality": 0.9, "arm": "left"},
    }
    controller.client.recognize.return_value = {
        "faces": [face],
        "best_match": face,
        "processing_ms": 100,
        "gesture": "pointing_up",
        "gesture_quality": 0.9,
        "gesture_arm": "left",
        "gesture_reason": "extended_arm_up",
        "gesture_status": "ok",
    }
    await controller.process(0)
    assert controller.result["person"] == "Saad"
    assert controller.result["gesture"] == "pointing_up"
    event, payload = controller.hass.bus.async_fire.call_args.args
    assert event == "seshat_face_recognized"
    assert payload["gesture_quality"] == 0.9 and payload["faces"][0]["gesture"]["arm"] == "left"


async def test_older_addon_defaults_gesture_to_disabled(controller):
    await controller.process(0)
    assert controller.result["gesture"] == "disabled"
    assert controller.available
