from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MovieData:
    """Structured movie metadata returned by scrapers."""

    number: str = ""
    title: str = ""
    original_title: str = ""
    studio: str = ""
    year: str = ""
    outline: str = ""
    runtime: str = ""
    director: str = ""
    actor: str = ""
    actor_list: list[str] = field(default_factory=list)
    actor_photo: dict[str, str] = field(default_factory=dict)
    release: str = ""
    cover: str = ""
    cover_small: str = ""
    trailer: str = ""
    website: str = ""
    series: str = ""
    label: str = ""
    tag: list[str] = field(default_factory=list)
    extrafanart: list[str] = field(default_factory=list)
    source: str = ""
    imagecut: int = 1
    uncensored: bool = False
    userrating: float | str = ""
    uservotes: int | str = ""
    # computed fields set during post-processing
    naming_rule: str = ""
    original_naming_rule: str = ""
    # extra headers for image download (javbus needs referer)
    headers: dict[str, str] = field(default_factory=dict)
    allow_number_change: bool = False


@dataclass(frozen=True)
class ProxyConfig:
    """Proxy configuration from config.ini."""

    enable: bool = False
    address: str = ""
    timeout: int = 5
    retry: int = 3
    proxytype: str = "socks5"

    SUPPORT_PROXY_TYPE = ("http", "socks5", "socks5h")

    def proxies(self) -> dict[str, str]:
        if not self.address:
            return {}
        if self.proxytype in self.SUPPORT_PROXY_TYPE:
            url = f"{self.proxytype}://{self.address}"
        else:
            url = f"http://{self.address}"
        return {"http": url, "https": url}
