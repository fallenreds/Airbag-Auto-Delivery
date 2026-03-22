import requests
import logging
import random
import time
from requests.exceptions import ConnectionError, RequestException, SSLError, Timeout
from config import HTTP_CONNECT_TIMEOUT, HTTP_READ_TIMEOUT


DEFAULT_HTTP_TIMEOUT = (HTTP_CONNECT_TIMEOUT, HTTP_READ_TIMEOUT)
HTTP_RETRY_ATTEMPTS = 3
HTTP_RETRY_BACKOFF_BASE_SECONDS = 0.5
HTTP_RETRY_BACKOFF_JITTER_RATIO = 0.2


def _retry_delay(attempt: int) -> float:
    base_delay = HTTP_RETRY_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
    jitter = random.uniform(0, base_delay * HTTP_RETRY_BACKOFF_JITTER_RATIO)
    return base_delay + jitter


def _is_transient_exception(error: Exception) -> bool:
    return isinstance(error, (Timeout, ConnectionError, SSLError))


def _request_with_retry(url: str, payload: dict):
    for attempt in range(1, HTTP_RETRY_ATTEMPTS + 1):
        try:
            response = requests.post(url, json=payload, timeout=DEFAULT_HTTP_TIMEOUT)
        except RequestException as error:
            if _is_transient_exception(error) and attempt < HTTP_RETRY_ATTEMPTS:
                delay = _retry_delay(attempt)
                logging.warning(
                    "http_retry_attempt service=nova_poshta method=POST url=%s attempt=%s max_attempts=%s reason=exception error_type=%s sleep_sec=%.3f",
                    url,
                    attempt,
                    HTTP_RETRY_ATTEMPTS,
                    type(error).__name__,
                    delay,
                )
                time.sleep(delay)
                continue
            raise

        if 500 <= response.status_code < 600 and attempt < HTTP_RETRY_ATTEMPTS:
            delay = _retry_delay(attempt)
            logging.warning(
                "http_retry_attempt service=nova_poshta method=POST url=%s attempt=%s max_attempts=%s reason=status_code status_code=%s sleep_sec=%.3f",
                url,
                attempt,
                HTTP_RETRY_ATTEMPTS,
                response.status_code,
                delay,
            )
            time.sleep(delay)
            continue

        return response


def ttn_tracking(documents: list):
    request = {
        "modelName": "TrackingDocument",
        "calledMethod": "getStatusDocuments",
        "methodProperties": {
            "Documents": documents

        }
    }
    url = 'https://api.novaposhta.ua/v2.0/json/'
    return _request_with_retry(url=url, payload=request).json(

    )
