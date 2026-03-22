import requests
from config import HTTP_CONNECT_TIMEOUT, HTTP_READ_TIMEOUT


DEFAULT_HTTP_TIMEOUT = (HTTP_CONNECT_TIMEOUT, HTTP_READ_TIMEOUT)


def ttn_tracking(documents: list):
    request = {
        "modelName": "TrackingDocument",
        "calledMethod": "getStatusDocuments",
        "methodProperties": {
            "Documents": documents

        }
    }
    url = 'https://api.novaposhta.ua/v2.0/json/'
    return requests.post(url, json=request, timeout=DEFAULT_HTTP_TIMEOUT).json(

    )
