from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class LogConfig:
    log_dir: str = "logs/"
    log_level: str = "INFO"
    logger_name: str = "onsrap"


class Logger:
    def __init__(self, log_dir: str | Path = "logs/", log_level: str = "INFO"):
        self.config = LogConfig(log_dir=str(log_dir), log_level=log_level)
        self.log_dir = Path(self.config.log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        logger_name = f"{self.config.logger_name}:{self.log_dir.resolve()}"
        self._logger = logging.getLogger(logger_name)
        if not getattr(self._logger, "_onsrap_configured", False):
            self._logger.setLevel(getattr(logging, self.config.log_level.upper(), logging.INFO))
            self._logger.propagate = False

            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(stream_handler)

            try:
                file_handler = logging.FileHandler(self.log_dir / "onsrap.log", encoding="utf-8")
                file_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
                self._logger.addHandler(file_handler)
            except OSError:
                pass

            setattr(self._logger, "_onsrap_configured", True)

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        message = " ".join(str(arg) for arg in args)
        if kwargs:
            context = json.dumps(kwargs, default=str, sort_keys=True)
            message = f"{message} | {context}" if message else context
        self._logger.info(message)

    def event(self, message: str, **kwargs: Any) -> None:
        if kwargs:
            self._logger.info("%s | %s", message, json.dumps(kwargs, default=str, sort_keys=True))
        else:
            self._logger.info(message)

