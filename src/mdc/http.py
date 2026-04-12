"""Consolidated HTTP client for all network requests."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from mdc.models import ProxyConfig

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0"
)


class TimeoutHTTPAdapter(HTTPAdapter):
    def __init__(self, *args, timeout=10, **kwargs):
        self.timeout = timeout
        super().__init__(*args, **kwargs)

    def send(self, request, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self.timeout
        return super().send(request, **kwargs)


def get_html(
    url: str,
    cookies: dict | None = None,
    ua: str | None = None,
    return_type: str | None = None,
    encoding: str | None = None,
    json_headers: dict | None = None,
    proxy_config: ProxyConfig | None = None,
    verify: str | bool | None = None,
    retry: int | None = None,
    timeout: int | None = None,
) -> str | bytes | requests.Response:
    """Core HTTP GET function with retry support."""
    # Import config lazily to avoid circular imports
    if proxy_config is None:
        from mdc.config import getInstance
        conf = getInstance()
        proxy_config = conf.proxy()
        if verify is None:
            verify = conf.cacert_file() or None

    _retry = retry if retry is not None else proxy_config.retry
    _timeout = timeout if timeout is not None else proxy_config.timeout

    headers = {"User-Agent": ua or USER_AGENT}
    if json_headers is not None:
        headers.update(json_headers)

    proxies = proxy_config.proxies() if proxy_config.enable else None
    errors = ""

    for i in range(_retry):
        try:
            result = requests.get(
                str(url),
                headers=headers,
                timeout=_timeout,
                proxies=proxies,
                verify=verify,
                cookies=cookies,
            )
            if return_type == "object":
                return result
            elif return_type == "content":
                return result.content
            else:
                result.encoding = encoding or result.apparent_encoding
                return result.text
        except Exception as e:
            logger.debug("Connect retry %d/%d for %s", i + 1, _retry, url)
            errors = str(e)

    if "getaddrinfo failed" in errors:
        logger.error("Connect failed! Please check your proxy config")
    else:
        logger.error("Connect failed: %s", errors)
    raise ConnectionError(f"Connect failed after {_retry} retries: {errors}")


def post_html(
    url: str,
    query: dict | str = None,
    headers: dict | None = None,
    proxy_config: ProxyConfig | None = None,
) -> requests.Response:
    if proxy_config is None:
        from mdc.config import getInstance
        proxy_config = getInstance().proxy()

    _headers = {"User-Agent": USER_AGENT}
    if headers:
        _headers.update(headers)

    proxies = proxy_config.proxies() if proxy_config.enable else None

    for i in range(proxy_config.retry):
        try:
            return requests.post(
                url,
                data=query,
                proxies=proxies,
                headers=_headers,
                timeout=proxy_config.timeout,
            )
        except Exception as e:
            logger.debug("POST retry %d/%d for %s", i + 1, proxy_config.retry, url)
            errors = str(e)
    raise ConnectionError(f"POST failed: {errors}")


def create_session(
    cookies: dict | None = None,
    ua: str | None = None,
    retry: int = 3,
    timeout: int = 10,
    proxies: dict | None = None,
    verify: str | bool | None = None,
) -> requests.Session:
    """Create a requests session with retry and keep-alive."""
    session = requests.Session()
    retries = Retry(
        total=retry,
        connect=retry,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    session.mount("https://", TimeoutHTTPAdapter(max_retries=retries, timeout=timeout))
    session.mount("http://", TimeoutHTTPAdapter(max_retries=retries, timeout=timeout))
    if isinstance(cookies, dict) and cookies:
        requests.utils.add_dict_to_cookiejar(session.cookies, cookies)
    if verify:
        session.verify = verify
    if proxies:
        session.proxies = proxies
    session.headers = {"User-Agent": ua or USER_AGENT}
    return session


def _download_one(args) -> str | None:
    """Download one file, used by parallel_download_files."""
    url, save_path, extra_headers = args
    try:
        filebytes = get_html(url, return_type="content", json_headers=extra_headers)
        if isinstance(filebytes, bytes) and filebytes:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with save_path.open("wb") as f:
                if len(filebytes) == f.write(filebytes):
                    return str(save_path)
    except Exception:
        pass
    return None


def parallel_download_files(
    dn_list, parallel: int = 0, extra_headers: dict | None = None
) -> list:
    """Download files in parallel using a thread pool."""
    mp_args = []
    for url, fullpath in dn_list:
        if (
            url
            and isinstance(url, str)
            and url.startswith("http")
            and fullpath
            and isinstance(fullpath, (str, Path))
        ):
            fullpath = Path(fullpath)
            fullpath.parent.mkdir(parents=True, exist_ok=True)
            mp_args.append((url, fullpath, extra_headers))
    if not mp_args:
        return []
    if not isinstance(parallel, int) or parallel not in range(1, 200):
        parallel = min(5, len(mp_args))
    with ThreadPoolExecutor(parallel) as pool:
        results = list(pool.map(_download_one, mp_args))
    return results
