# -*- coding: utf-8 -*-
"""HTTP request utilities for scrapers."""

import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/100.0.4896.133 Safari/537.36"
)
DEFAULT_TIMEOUT = 10


def get(
    url: str,
    cookies=None,
    ua: str = None,
    extra_headers=None,
    return_type: str = None,
    encoding: str = None,
    retry: int = 3,
    timeout: int = DEFAULT_TIMEOUT,
    proxies=None,
    verify=None,
) -> str | bytes | requests.Response:
    errors = ""
    headers = {"User-Agent": ua or USER_AGENT}
    if extra_headers is not None:
        headers.update(extra_headers)
    for i in range(retry):
        try:
            result = requests.get(
                url,
                headers=headers,
                timeout=timeout,
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
            logger.debug("Connect: %s retry %d/%d", url, i + 1, retry)
            errors = str(e)
    logger.debug("Connect failed: %s", errors)
    raise ConnectionError(f"Connect failed: {errors}")


def post(
    url: str,
    data=None,
    files=None,
    cookies=None,
    ua: str = None,
    return_type: str = None,
    encoding: str = None,
    retry: int = 3,
    timeout: int = DEFAULT_TIMEOUT,
    proxies=None,
    verify=None,
):
    errors = ""
    headers = {"User-Agent": ua or USER_AGENT}
    for i in range(retry):
        try:
            result = requests.post(
                url,
                data=data,
                files=files,
                headers=headers,
                timeout=timeout,
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
                return result
        except Exception as e:
            logger.debug("POST: %s retry %d/%d", url, i + 1, retry)
            errors = str(e)
    raise ConnectionError(f"POST failed: {errors}")


class TimeoutHTTPAdapter(HTTPAdapter):
    def __init__(self, *args, timeout=DEFAULT_TIMEOUT, **kwargs):
        self.timeout = timeout
        super().__init__(*args, **kwargs)

    def send(self, request, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self.timeout
        return super().send(request, **kwargs)


def request_session(
    cookies=None,
    ua: str = None,
    retry: int = 3,
    timeout: int = DEFAULT_TIMEOUT,
    proxies=None,
    verify=None,
):
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


def get_html_by_form(
    url,
    form_select=None,
    fields=None,
    cookies=None,
    ua=None,
    return_type=None,
    encoding=None,
    retry=3,
    timeout=DEFAULT_TIMEOUT,
    proxies=None,
    verify=None,
):
    try:
        import mechanicalsoup
    except ImportError:
        logger.warning("mechanicalsoup not installed, cannot use form-based requests")
        return None

    session = requests.Session()
    if isinstance(cookies, dict) and cookies:
        requests.utils.add_dict_to_cookiejar(session.cookies, cookies)
    retries = Retry(
        total=retry, connect=retry, backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    session.mount("https://", TimeoutHTTPAdapter(max_retries=retries, timeout=timeout))
    session.mount("http://", TimeoutHTTPAdapter(max_retries=retries, timeout=timeout))
    if verify:
        session.verify = verify
    if proxies:
        session.proxies = proxies
    try:
        browser = mechanicalsoup.StatefulBrowser(user_agent=ua or USER_AGENT, session=session)
        result = browser.open(url)
        if not result.ok:
            return None
        if isinstance(fields, dict):
            for k, v in fields.items():
                browser[k] = v
        response = browser.submit_selected()
        if return_type == "object":
            return response
        elif return_type == "content":
            return response.content
        elif return_type == "browser":
            return response, browser
        else:
            result.encoding = encoding or "utf-8"
            return response.text
    except Exception as e:
        logger.debug("get_html_by_form failed: %s", e)
    return None


def get_html_by_scraper(
    url=None,
    cookies=None,
    ua=None,
    return_type=None,
    encoding=None,
    retry=3,
    proxies=None,
    timeout=DEFAULT_TIMEOUT,
    verify=None,
):
    try:
        from cloudscraper import create_scraper
    except ImportError:
        logger.warning("cloudscraper not installed, falling back to requests")
        return get(url, cookies=cookies, ua=ua, return_type=return_type,
                   encoding=encoding, retry=retry, timeout=timeout,
                   proxies=proxies, verify=verify)

    session = create_scraper(browser={"custom": ua or USER_AGENT})
    if isinstance(cookies, dict) and cookies:
        requests.utils.add_dict_to_cookiejar(session.cookies, cookies)
    retries = Retry(
        total=retry, connect=retry, backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    session.mount("https://", TimeoutHTTPAdapter(max_retries=retries, timeout=timeout))
    session.mount("http://", TimeoutHTTPAdapter(max_retries=retries, timeout=timeout))
    if verify:
        session.verify = verify
    if proxies:
        session.proxies = proxies
    try:
        if isinstance(url, str) and url:
            result = session.get(str(url))
        else:
            return session
        if not result.ok:
            return None
        if return_type == "object":
            return result
        elif return_type == "content":
            return result.content
        elif return_type == "scraper":
            return result, session
        else:
            result.encoding = encoding or "utf-8"
            return result.text
    except Exception as e:
        logger.debug("get_html_by_scraper failed: %s", e)
    return None
