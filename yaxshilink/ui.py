from __future__ import annotations

import asyncio
import sys
from typing import Optional


CSI = "\x1b["


def clear_screen() -> str:
    # Clear screen and move cursor to home
    return f"{CSI}2J{CSI}H"


def progress_bar(percent: int, width: int = 40) -> str:
    percent = max(0, min(100, percent))
    filled = int(width * percent / 100)
    bar = "#" * filled + "-" * (width - filled)
    return f"[{bar}] {percent:3d}%"


class TerminalUI:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._last_lines = 0

    def _write(self, s: str):
        if not self.enabled:
            return
        sys.stdout.write(s)
        sys.stdout.flush()

    def reset(self):
        if not self.enabled:
            return
        self._write(clear_screen())
        self._last_lines = 0

    def show_lines(self, lines: list[str]):
        if not self.enabled:
            return
        self.reset()
        for ln in lines:
            self._write(ln + "\n")
        self._last_lines = len(lines)

    async def animate_until(self, title: str, done_evt: asyncio.Event, update_hint: Optional[str] = None):
        if not self.enabled:
            # If disabled, just wait silently
            await done_evt.wait()
            return
        percent = 0
        self.reset()
        while not done_evt.is_set():
            lines = [title, progress_bar(percent)]
            if update_hint:
                lines.append(update_hint)
            self.show_lines(lines)
            percent = (percent + 3) % 101
            await asyncio.sleep(0.05)
        # Final 100%
        self.show_lines([title, progress_bar(100)])
        await asyncio.sleep(0.05)

    async def run_with_progress(self, title: str, coro, update_hint: Optional[str] = None):
        done = asyncio.Event()

        async def _runner():
            try:
                return await coro
            finally:
                done.set()

        anim_task = asyncio.create_task(self.animate_until(title, done, update_hint))
        try:
            result = await _runner()
        finally:
            await done.wait()
            try:
                await anim_task
            except Exception:
                pass
            # Clear at the end to keep the terminal clean
            self.reset()
        return result

    def show_special(self, text: str):
        if not self.enabled:
            return
        self.show_lines([text])
