from __future__ import annotations

import curses
import re
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, List, Optional


@dataclass
class ParsedEvent:
    ts: str
    kind: str  # scanner|ws|arduino|session|system|error
    text: str


SCANNER_RE = re.compile(r"Scanner read:\s*(.+)")
SESSION_START_RE = re.compile(r"Session\s+(\d+)\s+started")
SESSION_CANCEL_RE = re.compile(r"Session\s+(\d+)\s+canceled")
BOTTLE_ACCEPT_RE = re.compile(r"Bottle accepted\s+([^\s]+)\s*\(([^)]*)\)")
WS_ERR_RE = re.compile(r"WebSocket error:")
WS_OK_RE = re.compile(r"WS OK:")
WS_CONN_RE = re.compile(r"WebSocket connected\.")
ARDUINO_END_RE = re.compile(r"Arduino ended session\.")


def parse_line(line: str) -> Optional[ParsedEvent]:
    # Expect format: "YYYY-mm-dd ... — LEVEL — message"
    parts = line.strip().split(" — ", 2)
    if len(parts) < 3:
        return None
    ts, level, msg = parts

    if SCANNER_RE.search(msg):
        code = SCANNER_RE.search(msg).group(1)
        return ParsedEvent(ts, "scanner", code)
    if SESSION_START_RE.search(msg):
        sid = SESSION_START_RE.search(msg).group(1)
        return ParsedEvent(ts, "session", f"Started #{sid}")
    if SESSION_CANCEL_RE.search(msg):
        sid = SESSION_CANCEL_RE.search(msg).group(1)
        return ParsedEvent(ts, "session", f"Canceled #{sid}")
    if BOTTLE_ACCEPT_RE.search(msg):
        m = BOTTLE_ACCEPT_RE.search(msg)
        code, material = m.group(1), m.group(2)
        return ParsedEvent(ts, "ws", f"Accepted {code} [{material}]")
    if "Bottle rejected" in msg:
        return ParsedEvent(ts, "ws", "Rejected")
    if WS_CONN_RE.search(msg):
        return ParsedEvent(ts, "ws", "Connected")
    if WS_OK_RE.search(msg):
        return ParsedEvent(ts, "ws", msg)
    if WS_ERR_RE.search(msg):
        return ParsedEvent(ts, "error", msg)
    if ARDUINO_END_RE.search(msg):
        return ParsedEvent(ts, "arduino", "Ended session")
    if "Arduino connected" in msg:
        return ParsedEvent(ts, "arduino", msg)
    if "Scanner connected" in msg:
        return ParsedEvent(ts, "scanner", msg)
    # default system
    return ParsedEvent(ts, "system", msg)


def _draw_panel(stdscr, y: int, x: int, w: int, title: str, lines: List[str]):
    stdscr.addstr(y, x, title, curses.A_BOLD)
    y += 1
    max_lines = curses.LINES - y - 1
    for i, s in enumerate(lines[-max_lines:]):
        stdscr.addstr(y + i, x, s[: w - 1])


def monitor_system_log(log_dir: Path, refresh_sec: float = 0.5):
    log_file = log_dir / "system.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    # Ensure file exists
    log_file.touch(exist_ok=True)

    # Deques to store recent events
    scanned: Deque[str] = deque(maxlen=20)
    ws_events: Deque[str] = deque(maxlen=20)
    session_events: Deque[str] = deque(maxlen=10)
    arduino_events: Deque[str] = deque(maxlen=10)
    other_events: Deque[str] = deque(maxlen=10)

    def _run(stdscr):
        curses.curs_set(0)
        stdscr.nodelay(True)
        pos = 0
        last_size = 0

        while True:
            try:
                size = log_file.stat().st_size
                if size < last_size:
                    # log rotated or truncated
                    pos = 0
                last_size = size
                with log_file.open("r", encoding="utf-8", errors="ignore") as f:
                    f.seek(pos)
                    for line in f:
                        ev = parse_line(line)
                        if not ev:
                            continue
                        if ev.kind == "scanner":
                            scanned.append(f"{ev.ts}  {ev.text}")
                        elif ev.kind == "ws":
                            ws_events.append(f"{ev.ts}  {ev.text}")
                        elif ev.kind == "session":
                            session_events.append(f"{ev.ts}  {ev.text}")
                        elif ev.kind == "arduino":
                            arduino_events.append(f"{ev.ts}  {ev.text}")
                        elif ev.kind == "error":
                            ws_events.append(f"{ev.ts}  {ev.text}")
                        else:
                            other_events.append(f"{ev.ts}  {ev.text}")
                    pos = f.tell()
            except Exception:
                pass

            stdscr.erase()
            h, w = stdscr.getmaxyx()
            col = max(1, w // 2)
            _draw_panel(stdscr, 0, 1, col - 2, "Scanner (last 20)", list(scanned))
            _draw_panel(stdscr, 0, col, w - col - 1, "WS & Results (last 20)", list(ws_events))
            _draw_panel(stdscr, h // 2, 1, col - 2, "Session (last 10)", list(session_events))
            _draw_panel(stdscr, h // 2, col, w - col - 1, "Arduino/System (last 10)", list(arduino_events) + list(other_events))

            stdscr.addstr(h - 1, 1, "q: quit  |  Monitoring logs/system.log  |  Refresh: %.1fs" % refresh_sec)
            stdscr.refresh()

            try:
                ch = stdscr.getch()
                if ch in (ord("q"), ord("Q")):
                    break
            except Exception:
                pass

            time.sleep(refresh_sec)

    curses.wrapper(_run)


def run_monitor(log_dir: str | Path, refresh_sec: float = 0.5):
    p = Path(log_dir)
    monitor_system_log(p, refresh_sec)
