from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import asyncio


@dataclass
class AppState:
    session_active: bool = False
    session_id: Optional[str] = None
    serial_writer: Optional[asyncio.StreamWriter] = None
    bottle_counter: int = 0
