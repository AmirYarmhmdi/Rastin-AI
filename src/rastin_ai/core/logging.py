"""File guide.

- Use: Configures application logging in one shared place.
- Usage: Import configure_logging from rastin_ai.core.logging.
- Duties: Defines configure_logging and related helper logic.
- Depends on: External packages only: logging.
"""

import logging

# This is the shared log format used by the backend.
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


# This sets up logging once, without removing handlers owned by other tools.
def configure_logging(log_level: str = "INFO") -> None:
    """Configure application logging in one place."""
    # Convert LOG_LEVEL text like "INFO" or "DEBUG" into a logging level.
    level = getattr(logging, log_level.upper(), logging.INFO)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    root_logger = logging.getLogger()

    root_logger.setLevel(level)

    # If no handler exists yet, add one for normal console logging.
    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        handler.setLevel(level)
        root_logger.addHandler(handler)
        return

    # If handlers already exist, update only missing pieces.
    for handler in root_logger.handlers:
        if handler.level == logging.NOTSET:
            handler.setLevel(level)
        if handler.formatter is None:
            handler.setFormatter(formatter)
