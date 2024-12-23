import logging
import sys
from typing import TextIO
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime
from time import perf_counter

import structlog
from structlog.contextvars import clear_contextvars, bind_contextvars
from structlog.types import EventDict, Processor
from rich.console import Console
from rich.traceback import Traceback
from typing import Literal

import config
import logging
import sys
from typing import TextIO
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime
from time import perf_counter

import structlog
from fastapi import Request, Response
from fastapi.middleware import Middleware
from structlog.types import EventDict, Processor
from rich.console import Console
from rich.traceback import Traceback
from asgi_correlation_id.context import correlation_id
from asgi_correlation_id import CorrelationIdMiddleware
from uvicorn.protocols.utils import get_path_with_query_string

def rich_custom_traceback(sio: TextIO, exc_info) -> None:
    """
    Pretty-print *exc_info* to *sio* using the *Rich* package.

    To be passed into `ConsoleRenderer`'s ``exception_formatter`` argument.
    """
    sio.write("\n")
    Console(file=sio, color_system="truecolor").print(
        Traceback.from_exception(*exc_info, show_locals=False)
    )


def drop_color_message_key(_, __, event_dict: EventDict) -> EventDict:
    """
    Uvicorn logs the message a second time in the extra `color_message`, but we don't
    need it. This processor drops the key from the event dict if it exists.
    """
    event_dict.pop("color_message", None)
    return event_dict


def setup_logging(log_level: Literal['INFO','DEBUG'] = "INFO"):
    timestamper = structlog.processors.TimeStamper(fmt='%d-%m-%Y %H:%M:%S:%f')

    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.stdlib.ExtraAdder(),
        drop_color_message_key,
        timestamper,
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    console_log_renderer = structlog.dev.ConsoleRenderer(
        sort_keys=False,
        exception_formatter=rich_custom_traceback)
    console_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            console_log_renderer,
        ],
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)


    file_log_renderer = structlog.processors.LogfmtRenderer(sort_keys=True)
    file_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            file_log_renderer,
        ],
    )

    logs_dir = Path(__name__).parent.parent.joinpath('logs')
    logs_dir.mkdir(parents=True, exist_ok=True)
    file_name = Path(__name__).parent.parent.joinpath(
            f'{logs_dir}/{datetime.now().strftime("%Y-%m-%d")}.log'
        )
    file_handler = RotatingFileHandler(
        file_name,
        maxBytes=5242880,
        backupCount=5,
    )
    file_handler.setFormatter(file_formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.setLevel(log_level.upper())

    for _log in ["uvicorn", "uvicorn.error"]:
        # Clear the log handlers for uvicorn loggers, and enable propagation
        # so the messages are caught by our root logger and formatted correctly
        # by structlog
        logging.getLogger(_log).handlers.clear()
        logging.getLogger(_log).propagate = True

    # Since we re-create the access logs ourselves, to add all information
    # in the structured log (see the `logging_middleware` in main.py), we clear
    # the handlers and prevent the logs to propagate to a logger higher up in the
    # hierarchy (effectively rendering them silent).
    logging.getLogger("uvicorn.access").handlers.clear()
    logging.getLogger("uvicorn.access").propagate = False

    def handle_exception(exc_type, exc_value, exc_traceback):
        """
        Log any uncaught exception instead of letting it be printed by Python
        (but leave KeyboardInterrupt untouched to allow users to Ctrl+C to stop)
        See https://stackoverflow.com/a/16993115/3641865
        """
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        root_logger.error(
            "Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback)
        )

    sys.excepthook = handle_exception


async def logging_middleware(request: Request, call_next) -> Response:
    access_logger = structlog.stdlib.get_logger("api.access")
    structlog.contextvars.clear_contextvars()
    # These context vars will be added to all log entries emitted during the request
    request_id = correlation_id.get()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    start_time = perf_counter()
    # If the call_next raises an error, we still want to return our own 500 response,
    # so we can add headers to it (process time, request ID...)
    response = Response(status_code=500)
    try:
        response = await call_next(request)
        if response.status_code == 200:
            return response
    except Exception:
        # TODO: Validate that we don't swallow exceptions (unit test?)
        structlog.stdlib.get_logger("api.error").exception("Uncaught exception")
        raise
    finally:

        process_time = perf_counter() - start_time
        status_code = response.status_code
        url = get_path_with_query_string(request.scope)
        client_host = request.client.host
        client_port = request.client.port
        http_method = request.method
        http_version = request.scope["http_version"]
        # Recreate the Uvicorn access log format, but add all parameters as structured information

        access_logger.info(
            f"""{client_host}:{client_port} - "{http_method} {url} HTTP/{http_version}" {status_code}""",
            network={"client": {"ip": client_host, "port": client_port}},
            duration=process_time,
        )
        response.headers["X-Process-Time"] = str(process_time)
        return response

setup_logging(log_level=config.LOG_LEVEL)

logger = structlog.stdlib.get_logger()
