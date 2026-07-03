import logging
import sys

from app.config import settings


def configure_logging() -> None:
    """
    Structured-ish logging setup: one line per log record with timestamp, level,
    logger name, and message, sent to stdout so it's picked up by `docker compose logs`
    or any container platform's log driver without extra config.
    """
    level = logging.DEBUG if settings.environment == "development" else logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Quiet down noisy third-party loggers so our own request/app logs stand out.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
