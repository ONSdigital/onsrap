from dataclasses import dataclass


class Logger:
    def __init__(self, log_dir: str = "logs/"):
        self.log_dir = log_dir
        # Initialize logging mechanism, e.g., create log files, set up logging format, etc.

    def event(self, message: str, **kwargs):
        # Log the event with the provided message and additional context from kwargs
        print(f"LOG: {message} | Context: {kwargs}")


@dataclass
class LogConfig:
    log_dir: str = "logs/"
    log_level: str = "INFO"

    