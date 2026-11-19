"""Low-overhead persistent Tapo L535E controller for python-kasa 0.12.0."""
import asyncio
import logging
import socket
import time
from collections import deque
from contextlib import suppress
from pathlib import Path

import keyring
from kasa import Credentials, Discover, LightState, Module

HOST = "192.168.1.22"
HERE = Path(__file__).resolve().parent
QUEUE = HERE / "pending"
LOG = HERE / "tapo_service.log"
PORT = 17354
POLL_INTERVAL = 0.05
CONNECT_TIMEOUT = 8
ACTION_TIMEOUT = 5
RECONNECT_DELAY = 1
PRESETS = ("1", "2", "3", "4", "5", "6")
BRIGHTNESS_STEPS = {"UP": 10, "DOWN": -10}
COLORS = {"7": (0, 100, 5), "8": (120, 100, 50), "9": (320, 80, 50)}

logging.basicConfig(filename=LOG, filemode="a", level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")


def read_credentials():
    username = keyring.get_password("TapoHotkeys", "username")
    password = keyring.get_password("TapoHotkeys", "password")
    if not username or not password:
        raise RuntimeError("Credentials missing: run setup_credentials.py")
    return Credentials(username, password)


async def close_device(dev):
    try:
        await dev.disconnect()
    except Exception:
        logging.exception("Failed to close device session")


async def connect():
    dev = None
    try:
        async with asyncio.timeout(CONNECT_TIMEOUT):
            credentials = await asyncio.to_thread(read_credentials)
            dev = await Discover.discover_single(HOST, credentials=credentials)
            await dev.update()
        return dev
    except (Exception, asyncio.CancelledError):
        if dev is not None:
            await close_device(dev)
        raise


def take_commands():
    files = []
    for path in QUEUE.glob("*.cmd"):
        try:
            files.append((path.stat().st_mtime_ns, path.name, path))
        except OSError:
            continue
    for _, _, path in sorted(files):
        try:
            action = path.read_text(encoding="utf-8-sig").strip()
            path.unlink()
        except OSError:
            continue
        except UnicodeError:
            logging.exception("Command file is not valid UTF-8: %s", path.name)
            with suppress(OSError):
                path.unlink()
            continue
        yield action
        if action == "STOP":
            return


def collect_commands(pending):
    if pending and pending[-1] == "STOP":
        return
    for action in take_commands():
        if action in COLORS and pending and pending[-1] in COLORS:
            pending[-1] = action
        elif (
            action in COLORS or action in PRESETS or action in BRIGHTNESS_STEPS
            or action in ("0", "STOP")
        ):
            pending.append(action)
        else:
            logging.warning("Ignoring invalid command: %r", action)


async def act(dev, action, state):
    if action == "0":
        if "on" not in state:
            await dev.update()
            state.update(on=bool(dev.is_on), brightness=int(dev.brightness))
        # Local state is fast, but may be stale after changes in the phone app.
        if state["on"]:
            await dev.turn_off()
        else:
            await dev.turn_on()
        state["on"] = not state["on"]
    elif action in PRESETS:
        # set_preset calls Light.set_state(), which sends device_on=True
        # together with color/brightness in a single request.
        await dev.features["light_preset"].set_value(f"Light preset {action}")
        state["on"] = True
        # Presets also set brightness. Query once on the *next* brightness action.
        state["brightness"] = None
    elif isinstance(action, str) and action in COLORS:
        hue, saturation, brightness = COLORS[action]
        # Atomic power-on + color change, avoiding default white flash.
        await dev.modules[Module.Light].set_state(
            LightState(light_on=True, hue=hue, saturation=saturation,
                       color_temp=0, brightness=brightness)
        )
        state["on"] = True
        state["brightness"] = brightness
    elif isinstance(action, list):
        if state.get("brightness") is None:
            await dev.update()
            state["brightness"] = int(dev.brightness)
            state["on"] = bool(dev.is_on)
        current = state["brightness"]
        target = current
        for step in action:
            target = min(100, max(1, target + step))
        if target != current or not state["on"]:
            # Brightness and power-on together in one device request.
            await dev.modules[Module.Light].set_state(
                LightState(light_on=True, brightness=target)
            )
            state["brightness"] = target
            state["on"] = True
        logging.info("Brightness: %s -> %s", current, target)
    else:
        raise ValueError(f"Unknown action: {action!r}")


async def main():
    QUEUE.mkdir(exist_ok=True)
    guard = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        guard.bind(("127.0.0.1", PORT))
        guard.listen(1)
    except OSError:
        logging.warning("Controller is already running")
        guard.close()
        return
    try:
        await run_controller()
    finally:
        guard.close()


async def run_controller():
    pending = deque()
    dev = None
    state = {}
    reconnect_at = 0
    connection = asyncio.create_task(connect())
    try:
        logging.info("Started (no-white-flash)")
        while True:
            collect_commands(pending)
            if pending and pending[0] == "STOP":
                logging.info("Stopped")
                return

            if connection is not None and connection.done():
                completed, connection = connection, None
                try:
                    dev = completed.result()
                except Exception:
                    logging.exception("Device connection failed. Dropping queued actions")
                    # Avoid applying commands unexpectedly when an offline bulb returns.
                    while pending and pending[0] != "STOP":
                        pending.popleft()
                    reconnect_at = time.monotonic() + RECONNECT_DELAY
                    continue
                state.update(on=bool(dev.is_on), brightness=int(dev.brightness))
                logging.info("Device ready")

            if not pending or dev is None:
                if pending and connection is None and time.monotonic() >= reconnect_at:
                    connection = asyncio.create_task(connect())
                if pending and connection is not None:
                    await asyncio.wait({connection}, timeout=POLL_INTERVAL)
                else:
                    await asyncio.sleep(POLL_INTERVAL)
                continue

            action = pending.popleft()
            if action in BRIGHTNESS_STEPS:
                steps = [BRIGHTNESS_STEPS[action]]
                while pending and pending[0] in BRIGHTNESS_STEPS:
                    steps.append(BRIGHTNESS_STEPS[pending.popleft()])
                action = steps

            started = time.monotonic()
            deadline = asyncio.timeout(ACTION_TIMEOUT)
            try:
                async with deadline:
                    await act(dev, action, state)
                logging.info("Action %s succeeded in %.2fs", action, time.monotonic() - started)
            except ValueError:
                logging.exception("Invalid device action: %s", action)
            except Exception:
                logging.exception("Action %s failed; refreshing state before the next relative action", action)
                state.clear()
                # Kasa handles its own session recovery. A service deadline can
                # interrupt that recovery, so discard that transport in this case.
                if deadline.expired():
                    await close_device(dev)
                    dev = None
                    reconnect_at = time.monotonic() + RECONNECT_DELAY
    finally:
        if connection is not None:
            connection.cancel()
            with suppress(asyncio.CancelledError, Exception):
                dev = await connection
        if dev is not None:
            await close_device(dev)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        logging.exception("Fatal controller error")
