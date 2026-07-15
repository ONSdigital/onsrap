from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class LogConfig:
    """
    Data class which holds information regarding how the logs are set up.

    Parameters
    ----------
    ``log_dir`` : str, default = "logs/"
        The directory where all logs are stored for the Pipeline. 
    ``log_level`` : str, default = "INFO"
        Denotes how severe the log message is. 
    ``logger_name`` : str, default = "onsrap"
        The name of the logging system.
    """
    log_dir: str = "logs/"
    log_level: str = "INFO"
    logger_name: str = "onsrap"


class Logger:
    """
    Creates a logging system. 

    This system creates a logging directory and enables writing the log messages
    to both console and the logging files. It allows configurable logging levels
    to adjust for severity and avoids duplicating logging messages or handlers. 
    If the logger is unable to write to a file, the logging continues using only 
    the console handler.

    Parameters
    ----------
    ``log_dir`` : str or Path, default = "logs/"
        The directory where you'd like your logs stored. 
    ``log_level`` : str, default = "INFO" 
        The severity of the log. 
    """
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
        """
        Converts Logger instances to be callable, enabling easier implementation
        of logging. 

        Positional arguemnts are converted to strings and joined with spaces. 
        Keyword arguments are serialised as JSON and appended as structured 
        context.
        """
        message = " ".join(str(arg) for arg in args)
        if kwargs:
            context = json.dumps(kwargs, default=str, sort_keys=True)
            message = f"{message} | {context}" if message else context
        self._logger.info(message)

    def event(self, message: str, **kwargs: Any) -> None:
        """
        Logs a named event with optional structured context. 

        Parameters
        ----------
        ``message`` : str 
            The main description of the event to be logged. 
        ``**kwargs`` : Any 
            Additional information to be recorded in the log record. 
        """
        if kwargs:
            self._logger.info("%s | %s", message, json.dumps(kwargs, default=str, sort_keys=True))
        else:
            self._logger.info(message)

    def warning(self, message: str, **kwargs: Any) -> None:
        """
        Logs a warning message with optional structured context. 

        Parameters
        ----------
        ``message`` : str 
            The main description of the warning to be logged. 
        ``**kwargs`` : Any 
            Additional information to be recorded in the log record. 
        """
        if kwargs:
            self._logger.warning("%s | %s", message, json.dumps(kwargs, default=str, sort_keys=True))
        else:
            self._logger.warning(message)