from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional


_loggers: Dict[str, logging.Logger] = {}


def get_logger(log_dir: Path, session_id: Optional[int] = None) -> logging.Logger:
    """Create or get a logger instance for system or session."""
    name = f"session_{session_id}" if session_id else "system"
    log_dir.mkdir(exist_ok=True, parents=True)
    log_file = log_dir / f"{name}.log"

    if name not in _loggers:
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s — %(levelname)s — %(message)s")
        )
        logger.addHandler(handler)
        _loggers[name] = logger
    return _loggers[name]
