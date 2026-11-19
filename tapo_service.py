"""Low-overhead persistent Tapo L535E controller for python-kasa 0.12.0."""
import asyncio
import logging
import socket
import time
from pathlib import Path

import keyring
from kasa import Credentials, Discover, LightState, Module

HOST = "192.168.1.22"
HERE = Path(__file__).resolve().parent
QUEUE = HERE / "pending"
LOG = HERE / "tapo_service.log"
PORT = 17354
COLORS = {"7": (0, 100, 5), "8": (120, 100, 50), "9": (320, 80, 50)}

logging.basicConfig(filename=LOG, filemode="a", level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

async def connect():
    username = keyring.get_password("TapoHotkeys", "username")
    password = keyring.get_password("TapoHotkeys", "password")
    if not username or not password:
        raise RuntimeError("Credentials missing: run setup_credentials.py")
    dev = await Discover.discover_single(HOST, credentials=Credentials(username, password))
    await dev.update()
    return dev


def take_commands():
    files = sorted(QUEUE.glob("*.cmd"), key=lambda p: p.stat().st_mtime_ns)
    actions = []
    for path in files:
        try:
            action = path.read_text(encoding="utf-8-sig").strip()
            path.unlink()
            actions.append(action)
        except OSError:
            continue
    # Collapse consecutive brightness keys into one Wi-Fi command.
    merged = []
    for a in actions:
        if a in ("UP", "DOWN"):
            step = 1 if a == "UP" else -1
            if merged and isinstance(merged[-1], int):
                merged[-1] += step
            else:
                merged.append(step)
        else:
            merged.append(a)
    return [a for a in merged if a != 0]


async def act(dev, action, state):
    if action == "0":
        # Local state is fast, but may be stale after changes in the phone app.
        if state["on"]:
            await dev.turn_off()
        else:
            await dev.turn_on()
        state["on"] = not state["on"]
    elif action in ("1", "2", "3", "4", "5", "6"):
        # set_preset calls Light.set_state(), which sends device_on=True
        # together with color/brightness in a single request.
        await dev.features["light_preset"].set_value(f"Light preset {action}")
        state["on"] = True
        # Presets also set brightness. Query once on the *next* brightness action.
        state["brightness"] = None
    elif action in COLORS:
        hue, saturation, brightness = COLORS[action]
        # Atomic power-on + color change, avoiding default white flash.
        await dev.modules[Module.Light].set_state(
            LightState(light_on=True, hue=hue, saturation=saturation,
                       color_temp=0, brightness=brightness)
        )
        state["on"] = True
        state["brightness"] = brightness
    elif isinstance(action, int):
        if state["brightness"] is None:
            await dev.update()
            state["brightness"] = int(dev.brightness)
            state["on"] = bool(dev.is_on)
        current = state["brightness"]
        target = min(100, max(1, current + action * 10))
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
    dev = None
    state = {}
    try:
        logging.info("Started (no-white-flash)")
        while True:
            actions = take_commands()
            if not actions:
                await asyncio.sleep(0.05)
                continue
            for action in actions:
                if action == "STOP":
                    logging.info("Stopped")
                    return
                started = time.monotonic()
                for attempt in range(2):
                    try:
                        if dev is None:
                            dev = await connect()
                            state = {"on": bool(dev.is_on),
                                     "brightness": int(dev.brightness)}
                        await act(dev, action, state)
                        logging.info("Action %s succeeded in %.2fs", action,
                                     time.monotonic() - started)
                        break
                    except Exception:
                        logging.exception("Action %s failed (attempt %s)", action, attempt + 1)
                        if dev is not None:
                            try:
                                await dev.disconnect()
                            except Exception:
                                pass
                        dev = None
    finally:
        if dev is not None:
            await dev.disconnect()
        guard.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        logging.exception("Fatal controller error")
