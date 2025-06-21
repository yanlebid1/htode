# common/utils/unified_request_utils.py

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, Dict, Any, Union

# Import the logging utilities from the new logging modules
from common.utils.logging_config import log_operation, log_context

# Import the common utils logger
from . import logger

# Common constants
DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_FACTOR = 0.3
DEFAULT_STATUS_FORCELIST = (500, 502, 504)

# Default headers for HTTP requests
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:134.0) Gecko/20100101 Firefox/134.0",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br, zstd",
}

# API base URLs
BASE_FLATFY_URL = "https://flatfy.ua/api/realties"


@log_operation("get_retry_session")
def get_retry_session(
    retries: int = DEFAULT_RETRIES,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    status_forcelist: tuple = DEFAULT_STATUS_FORCELIST,
    session: Optional[requests.Session] = None,
) -> requests.Session:
    """
    Get requests session with retry configuration.
    """
    with log_context(logger, retries=retries, backoff_factor=backoff_factor):
        session = session or requests.Session()
        retry = Retry(
            total=retries,
            read=retries,
            connect=retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
            allowed_methods=["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        logger.debug(
            "Configured session with retry",
            extra={
                "retries": retries,
                "backoff_factor": backoff_factor,
                "status_forcelist": status_forcelist,
            },
        )

        return session


@log_operation("make_request")
def make_request(
    url: str,
    method: str = "get",
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: Union[float, tuple] = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    session: Optional[requests.Session] = None,
    jitter: bool = True,
    raise_for_status: bool = True,
) -> Optional[requests.Response]:
    """
    Make HTTP request with retries and proper error handling
    """
    with log_context(logger, url=url, method=method, retries=retries):
        session = get_retry_session(retries=retries, session=session)

        # Create default headers if none provided
        if not headers:
            headers = DEFAULT_HEADERS.copy()

        method = method.lower()

        try:
            logger.debug(
                f"Making {method.upper()} request",
                extra={"url": url, "method": method, "timeout": timeout},
            )

            if method == "get":
                response = session.get(
                    url, params=params, headers=headers, timeout=timeout
                )
            elif method == "post":
                response = session.post(
                    url,
                    params=params,
                    data=data,
                    json=json,
                    headers=headers,
                    timeout=timeout,
                )
            elif method == "put":
                response = session.put(
                    url,
                    params=params,
                    data=data,
                    json=json,
                    headers=headers,
                    timeout=timeout,
                )
            elif method == "delete":
                response = session.delete(
                    url,
                    params=params,
                    data=data,
                    json=json,
                    headers=headers,
                    timeout=timeout,
                )
            else:
                logger.error("Unsupported HTTP method", extra={"method": method})
                raise ValueError(f"Unsupported HTTP method: {method}")

            if raise_for_status:
                response.raise_for_status()

            logger.debug(
                "Request successful",
                extra={
                    "url": url,
                    "status_code": response.status_code,
                    "response_time": response.elapsed.total_seconds(),
                },
            )

            return response

        except requests.exceptions.HTTPError as e:
            logger.error(
                "HTTP Error",
                exc_info=True,
                extra={
                    "url": url,
                    "error_type": type(e).__name__,
                    "status_code": (
                        e.response.status_code if hasattr(e, "response") else None
                    ),
                },
            )
            if raise_for_status:
                raise
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(
                "Connection Error",
                exc_info=True,
                extra={"url": url, "error_type": type(e).__name__},
            )
            if raise_for_status:
                raise
            return None
        except requests.exceptions.Timeout as e:
            logger.error(
                "Timeout Error",
                exc_info=True,
                extra={"url": url, "error_type": type(e).__name__, "timeout": timeout},
            )
            if raise_for_status:
                raise
            return None
        except requests.exceptions.RequestException as e:
            logger.error(
                "Request Error",
                exc_info=True,
                extra={"url": url, "error_type": type(e).__name__},
            )
            if raise_for_status:
                raise
            return None


# ===== API-Specific Utility Functions =====


@log_operation("fetch_ads_flatfy")
def fetch_ads_flatfy(
    geo_id=None,
    page=1,
    room_count=None,
    price_min=None,
    price_max=None,
    section_id=2,
    # Additional optional params:
    currency="UAH",
    group_collapse="1",
    has_eoselia="false",
    is_without_fee="false",
    lang="uk",
    price_sqm_currency="UAH",
    sort="insert_time",
) -> list:
    """
    Fetch a list of ad dicts from flatfy.ua API with shared logic.
    """
    with log_context(logger, geo_id=geo_id, page=page, section_id=section_id):
        try:
            params = {
                "geo_id": geo_id,
                "page": page,
                "section_id": section_id,
                "currency": currency,
                "group_collapse": group_collapse,
                "has_eoselia": has_eoselia,
                "is_without_fee": is_without_fee,
                "lang": lang,
                "price_sqm_currency": price_sqm_currency,
                "sort": sort,
            }

            if room_count:
                params["room_count"] = room_count
            if price_min is not None:
                params["price_min"] = str(price_min)
            if price_max is not None:
                params["price_max"] = str(price_max)

            logger.info(
                "Fetching Flatfy ads", extra={"url": BASE_FLATFY_URL, "params": params}
            )

            # Use our make_request utility
            response = make_request(
                BASE_FLATFY_URL,
                method="get",
                params=params,
                headers=DEFAULT_HEADERS,
                timeout=15,
                retries=3,
            )

            if response is None or response.status_code != 200:
                logger.error(
                    "Failed to fetch ads from Flatfy",
                    extra={
                        "status_code": (
                            response.status_code if response else "No response"
                        ),
                        "params": params,
                    },
                )
                return []

            data = response.json().get("data", [])
            logger.info(
                "Successfully fetched ads from Flatfy",
                extra={"ad_count": len(data), "page": page},
            )
            return data
        except Exception as e:
            logger.error(
                "Error fetching ads from Flatfy",
                exc_info=True,
                extra={"error_type": type(e).__name__, "params": params},
            )
            return []


# ===== Convenience Wrappers =====


@log_operation("get_json")
def get_json(url: str, **kwargs) -> Optional[Dict[str, Any]]:
    """
    Convenience wrapper to make a GET request and return JSON data.
    """
    with log_context(logger, url=url):
        response = make_request(url, method="get", **kwargs)
        if response and response.status_code == 200:
            try:
                json_data = response.json()
                logger.debug(
                    "Successfully parsed JSON response",
                    extra={"url": url, "data_size": len(str(json_data))},
                )
                return json_data
            except ValueError as e:
                logger.error(
                    "Failed to parse JSON response",
                    exc_info=True,
                    extra={"url": url, "error_type": type(e).__name__},
                )
        return None


@log_operation("post_json")
def post_json(url: str, data: Dict[str, Any], **kwargs) -> Optional[Dict[str, Any]]:
    """
    Convenience wrapper to make a POST request with JSON data and return JSON response.
    """
    with log_context(logger, url=url, data_size=len(str(data))):
        response = make_request(url, method="post", json=data, **kwargs)
        if response and response.status_code in (200, 201, 202):
            try:
                json_response = response.json()
                logger.debug(
                    "Successfully parsed JSON response",
                    extra={
                        "url": url,
                        "status_code": response.status_code,
                        "response_size": len(str(json_response)),
                    },
                )
                return json_response
            except ValueError as e:
                logger.error(
                    "Failed to parse JSON response",
                    exc_info=True,
                    extra={"url": url, "error_type": type(e).__name__},
                )
        return None


@log_operation("download_file")
def download_file(url: str, local_path: str, **kwargs) -> bool:
    """
    Download a file from a URL to a local path.
    """
    with log_context(logger, url=url, local_path=local_path):
        # Set stream=True to avoid loading the whole file into memory
        kwargs["stream"] = True

        response = make_request(url, **kwargs)
        if not response:
            return False

        try:
            with open(local_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info(
                "Successfully downloaded file",
                extra={
                    "url": url,
                    "local_path": local_path,
                    "file_size": response.headers.get("content-length", "unknown"),
                },
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to save downloaded file",
                exc_info=True,
                extra={
                    "url": url,
                    "local_path": local_path,
                    "error_type": type(e).__name__,
                },
            )
            return False
