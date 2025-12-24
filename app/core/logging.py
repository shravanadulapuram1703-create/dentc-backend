import logging
import sys
from logging.config import dictConfig
# from app.core.logging_filter import ContextFilter


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,

    "filters": {
        "context": {
            "()": "app.core.logging_filter.ContextFilter",
        }
    },

    "formatters": {
        "default": {
            "format": (
                "%(asctime)s | %(levelname)s | "
                "%(name)s | "
                "req_id=%(request_id)s | "
                "user=%(user_id)s | "
                "tenant=%(tenant)s | "
                "%(message)s"
            )
        }
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "default",
            "filters": ["context"],   # attach filter here
        }
    },

    "root": {
        "level": "DEBUG",
        "handlers": ["console"],
    },
    "loggers": {"uvicorn": {
                    "level": "INFO",
                    "handlers": ["console"],
                    "propagate": False,
                },
                "uvicorn.error": {
                    "level": "INFO",
                    "handlers": ["console"],
                    "propagate": False,
                },
                "uvicorn.access": {
                    "level": "INFO",
                    "handlers": ["console"],
                    "propagate": False,
                },
            },

}


def setup_logging():
    dictConfig(LOGGING_CONFIG)
    # logging.getLogger().addFilter(ContextFilter())

