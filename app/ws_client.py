from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

import websockets

from .config import Config
from .state import AppState


def _now_utc_iso() -> str:
    return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _material_to_cmd(material: Optional[str]) -> str:
    if not material:
        return "R"
    m = material.lower()
    if m.startswith("plast"):
        return "P"
    if m.startswith("alum"):
        return "A"
    return "R"


def _generate_code(state: AppState, cfg: Config) -> str:
    state.bottle_counter += 1
    return f"BTL-{int(cfg.fandomat_id):03d}-{state.bottle_counter:05d}"


async def websocket_listener(
    state: AppState,
    cfg: Config,
    get_logger: Callable[[Optional[int]], any],
    send_to_arduino_coro: Callable[[str], Awaitable[None]],
    on_send_ready: Callable[[Callable[[dict], Awaitable[None]]], None],
):
    """New protocol: HELLO auth, JSON PING/PONG, session/events per spec.

    on_send_ready will be called with an async function send_message(payload: dict)
    that sends JSON over the active websocket. On reconnect it will be updated.
    """
    sys_logger = get_logger(None)
    print(f"\n🔗 WebSocket: {cfg.ws_url}")

    inactivity_task: Optional[asyncio.Task] = None
    last_activity: float = 0.0

    async def schedule_inactivity_checker(send_message: Callable[[dict], Awaitable[None]]):
        nonlocal inactivity_task, last_activity

        async def _checker():
            while state.session_active and state.session_id:
                await asyncio.sleep(5)
                if last_activity and (asyncio.get_event_loop().time() - last_activity) > 90:
                    # Send SESSION_END
                    payload = {"type": "SESSION_END", "session_id": state.session_id}
                    await send_message(payload)
                    state.session_active = False
                    await send_to_arduino_coro("E")
                    sys_logger.info("Auto SESSION_END after inactivity.")
                    break

        if inactivity_task and not inactivity_task.done():
            inactivity_task.cancel()
        inactivity_task = asyncio.create_task(_checker())

    while True:
        try:
            async with websockets.connect(cfg.ws_url) as ws:
                print("✅ WebSocket connected. Authenticating...\n")
                sys_logger.info("WebSocket connected.")

                async def send_message(payload: dict):
                    await ws.send(json.dumps(payload))

                # Expose sender to outside world (scanner, etc.)
                on_send_ready(send_message)

                # HELLO auth
                await send_message(
                    {
                        "type": "HELLO",
                        "fandomat_id": int(cfg.fandomat_id),
                        "device_token": cfg.device_token,
                        "version": cfg.version,
                    }
                )

                # Listen loop
                async for raw in ws:
                    try:
                        data = json.loads(raw)
                    except Exception:
                        continue

                    msg_type = data.get("type")

                    if msg_type == "OK":
                        sys_logger.info(f"WS OK: {data.get('message', '')}")

                    elif msg_type == "ERROR":
                        sys_logger.error(f"WS ERROR: {data.get('error', '')}")

                    elif msg_type == "PING":
                        await send_message({"type": "PONG"})

                    elif msg_type == "START_SESSION":
                        # Activate
                        session_id = data.get("session_id")
                        state.session_id = session_id
                        state.session_active = True
                        last_activity = asyncio.get_event_loop().time()

                        logger = get_logger(session_id)
                        print(f"\n🟢 Session started: {session_id}")
                        logger.info(f"Session {session_id} started")
                        await send_to_arduino_coro("S")

                        # Confirm
                        await send_message({"type": "SESSION_STARTED", "session_id": session_id})

                        await schedule_inactivity_checker(send_message)

                    elif msg_type == "CANCEL_SESSION":
                        if data.get("session_id") == state.session_id:
                            state.session_active = False
                            print(f"\n🛑 Session canceled: {state.session_id}")
                            sys_logger.info(f"Session {state.session_id} canceled: {data.get('reason','')}")
                            await send_to_arduino_coro("E")

                    elif msg_type == "BOTTLE_CHECK_RESULT":
                        # This is response to our CHECK_BOTTLE
                        exist = data.get("exist")
                        sid = data.get("session_id")
                        if sid != state.session_id or not state.session_active:
                            continue

                        if exist:
                            bottle = data.get("bottle") or {}
                            material = bottle.get("material")
                            cmd = _material_to_cmd(material)
                            await send_to_arduino_coro(cmd)

                            # Send BOTTLE_ACCEPTED
                            code = _generate_code(state, cfg)
                            await send_message(
                                {
                                    "type": "BOTTLE_ACCEPTED",
                                    "session_id": sid,
                                    "code": code,
                                    "material": material or "unknown",
                                    "timestamp": _now_utc_iso(),
                                }
                            )
                            last_activity = asyncio.get_event_loop().time()
                            sys_logger.info(f"Bottle accepted {code} ({material})")
                        else:
                            await send_to_arduino_coro("R")
                            sys_logger.info("Bottle rejected (not found)")

        except Exception as e:
            sys_logger.error(f"WebSocket error: {e}")
            print("❌ WebSocket connection lost. Retrying in 3s...")
            await asyncio.sleep(3)
