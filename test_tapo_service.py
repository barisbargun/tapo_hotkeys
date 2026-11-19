import asyncio
import os
import tempfile
import unittest
from collections import deque
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import tapo_service as service
from kasa.exceptions import TimeoutError as KasaTimeoutError


def fake_device(brightness=50, is_on=True):
    light = Mock(set_state=AsyncMock())
    return Mock(
        brightness=brightness,
        is_on=is_on,
        modules={service.Module.Light: light},
        features={"light_preset": Mock(set_value=AsyncMock())},
        update=AsyncMock(),
        disconnect=AsyncMock(),
        turn_on=AsyncMock(),
        turn_off=AsyncMock(),
    )


class ControllerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.queue = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.multiple(
            service, QUEUE=self.queue, PORT=0, POLL_INTERVAL=0.001, RECONNECT_DELAY=0,
        ))
        self.sequence = 0

    def enqueue(self, *actions):
        paths = []
        for action in actions:
            self.sequence += 1
            path = self.queue / f"{self.sequence:04d}.cmd"
            path.write_text(action, encoding="utf-8-sig")
            os.utime(path, (1_700_000_000, 1_700_000_000))
            paths.append(path)
        return paths

    async def wait_until(self, condition):
        async with asyncio.timeout(2):
            while not condition():
                await asyncio.sleep(0.001)

    def start(self):
        task = asyncio.create_task(service.main())
        self.addAsyncCleanup(self.cancel, task)
        return task

    async def cancel(self, task):
        if not task.done():
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

    async def test_warmup_starts_before_input_and_coalesces_pending_colors(self):
        started = asyncio.Event()
        ready = asyncio.Event()
        device = fake_device(is_on=False)

        async def connect():
            started.set()
            await ready.wait()
            return device

        with patch.object(service, "connect", side_effect=connect) as connection:
            controller = self.start()
            await asyncio.wait_for(started.wait(), 2)
            first, = self.enqueue("7")
            await self.wait_until(lambda: not first.exists())
            self.enqueue("8", "9", "STOP")
            ready.set()
            await asyncio.wait_for(controller, 2)

        connection.assert_awaited_once()
        light = device.modules[service.Module.Light]
        light.set_state.assert_awaited_once_with(service.LightState(
            light_on=True, hue=320, saturation=80, color_temp=0, brightness=50,
        ))
        device.turn_on.assert_not_awaited()
        device.disconnect.assert_awaited_once()

    async def test_queued_colors_coalesce_while_a_write_is_in_flight(self):
        started = asyncio.Event()
        finished = asyncio.Event()
        device = fake_device()

        async def write(state):
            if state.hue == 0:
                started.set()
                await finished.wait()

        light = device.modules[service.Module.Light]
        light.set_state.side_effect = write
        with patch.object(service, "connect", return_value=device) as connection:
            self.enqueue("7")
            controller = self.start()
            await asyncio.wait_for(started.wait(), 2)
            self.enqueue("8", "9", "STOP")
            finished.set()
            await asyncio.wait_for(controller, 2)

        self.assertEqual([call.args[0].hue for call in light.set_state.await_args_list], [0, 320])
        connection.assert_awaited_once()

    async def test_command_order_and_brightness_clamping(self):
        device = fake_device(brightness=100)
        light = device.modules[service.Module.Light]
        calls = Mock()
        calls.attach_mock(light.set_state, "write")
        calls.attach_mock(device.turn_off, "off")
        calls.attach_mock(device.features["light_preset"].set_value, "preset")
        with patch.object(service, "connect", return_value=device):
            self.enqueue("UP", "DOWN", "7", "0", "8", "2", "9", "STOP")
            await asyncio.wait_for(self.start(), 2)

        self.assertEqual(
            [call[0] for call in calls.mock_calls],
            ["write", "write", "off", "write", "preset", "write"],
        )
        self.assertEqual(light.set_state.await_args_list[0].args[0].brightness, 90)

    async def test_brightness_after_preset_refreshes_before_writing(self):
        device = fake_device(brightness=50)
        preset = device.features["light_preset"].set_value
        light = device.modules[service.Module.Light]

        async def refresh():
            device.brightness = 70

        device.update.side_effect = refresh
        with patch.object(service, "connect", return_value=device) as connection:
            self.enqueue("2", "UP", "STOP")
            await asyncio.wait_for(self.start(), 2)

        preset.assert_awaited_once_with("Light preset 2")
        device.update.assert_awaited_once()
        light.set_state.assert_awaited_once_with(service.LightState(light_on=True, brightness=80))
        connection.assert_awaited_once()

    async def test_ambiguous_toggle_is_not_replayed_and_session_is_reused(self):
        device = fake_device()

        async def applied_but_no_reply():
            device.is_on = False
            raise KasaTimeoutError("reply lost")

        device.turn_off.side_effect = applied_but_no_reply
        with patch.object(service, "connect", return_value=device) as connection:
            self.enqueue("0", "0", "STOP")
            await asyncio.wait_for(self.start(), 2)

        device.turn_off.assert_awaited_once()
        device.update.assert_awaited_once()
        device.turn_on.assert_awaited_once()
        connection.assert_awaited_once()

    async def test_ambiguous_brightness_is_not_replayed(self):
        device = fake_device()
        light = device.modules[service.Module.Light]

        async def applied_but_no_reply(state):
            device.brightness = state.brightness
            raise KasaTimeoutError("reply lost")

        light.set_state.side_effect = applied_but_no_reply
        with patch.object(service, "connect", return_value=device):
            self.enqueue("UP", "STOP")
            await asyncio.wait_for(self.start(), 2)

        light.set_state.assert_awaited_once_with(service.LightState(light_on=True, brightness=60))
        self.assertEqual(device.brightness, 60)

    async def test_stop_closes_device_during_warmup(self):
        updating = asyncio.Event()
        device = fake_device()

        async def update():
            updating.set()
            await asyncio.Future()

        device.update.side_effect = update
        with patch.object(service, "read_credentials", return_value=service.Credentials("test", "test")), patch.object(
            service.Discover, "discover_single", return_value=device,
        ):
            controller = self.start()
            await asyncio.wait_for(updating.wait(), 2)
            self.enqueue("STOP")
            await asyncio.wait_for(controller, 2)

        device.disconnect.assert_awaited_once()

    async def test_action_deadline_replaces_session_without_resending(self):
        old, new = fake_device(), fake_device(is_on=False)

        async def no_reply():
            await asyncio.Future()

        old.turn_off.side_effect = no_reply
        with patch.object(service, "ACTION_TIMEOUT", 0.02), patch.object(
            service, "connect", side_effect=[old, new],
        ) as connection:
            self.enqueue("0", "8", "STOP")
            await asyncio.wait_for(self.start(), 2)

        old.turn_off.assert_awaited_once()
        old.disconnect.assert_awaited_once()
        new.turn_off.assert_not_awaited()
        new.modules[service.Module.Light].set_state.assert_awaited_once()
        self.assertEqual(connection.await_count, 2)

    async def test_connection_failure_drops_stale_commands_and_new_input_recovers(self):
        device = fake_device()
        light = device.modules[service.Module.Light]
        with patch.object(
            service, "connect", side_effect=[OSError("offline"), device],
        ) as connection, patch.object(service.logging, "exception") as report:
            self.enqueue("7", "0")
            controller = self.start()
            await self.wait_until(lambda: report.called)
            self.enqueue("9", "STOP")
            await asyncio.wait_for(controller, 2)

        self.assertEqual(connection.await_count, 2)
        device.turn_off.assert_not_awaited()
        light.set_state.assert_awaited_once()
        self.assertEqual(light.set_state.await_args.args[0].hue, 320)

    async def test_queue_ignores_temporary_files_and_leaves_commands_after_stop(self):
        self.enqueue("7", "8", "STOP", "0")
        temporary = self.queue / "incomplete.tmp"
        temporary.write_text("9", encoding="utf-8")
        pending = deque()
        service.collect_commands(pending)
        service.collect_commands(pending)
        self.assertEqual(list(pending), ["8", "STOP"])
        self.assertEqual(sorted(path.name for path in self.queue.iterdir()), [
            "0004.cmd", "incomplete.tmp",
        ])
