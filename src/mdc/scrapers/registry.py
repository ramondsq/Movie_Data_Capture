# -*- coding: utf-8 -*-
"""Scraper source selection and search dispatch."""

from __future__ import annotations

import importlib
import logging
import re
from dataclasses import dataclass, field

from mdc.models import MovieData
from mdc.scrapers.base import Parser

logger = logging.getLogger(__name__)


@dataclass
class SearchContext:
    """Context passed to scrapers during search."""
    proxies: dict | None = None
    verify: str | None = None
    specifiedSource: str | None = None
    specifiedUrl: str | None = None
    dbcookies: dict | None = None
    dbsite: str = ""
    morestoryline: bool = False
    debug: bool = False


ADULT_SOURCES = [
    "javlibrary", "javdb", "javbus", "airav", "fanza", "xcity", "jav321",
    "mgstage", "fc2", "avsox", "dlsite", "carib", "madou", "msin",
    "getchu", "gcolle", "javday", "pissplay", "javmenu", "pcolle", "caribpr",
]

GENERAL_SOURCES = ["tmdb", "imdb"]


def search(number: str, sources: str = None, **kwargs) -> MovieData | None:
    ctx = SearchContext(
        proxies=kwargs.get("proxies"),
        verify=kwargs.get("verify"),
        specifiedSource=kwargs.get("specifiedSource"),
        specifiedUrl=kwargs.get("specifiedUrl"),
        dbcookies=kwargs.get("dbcookies"),
        dbsite=kwargs.get("dbsite", ""),
        morestoryline=kwargs.get("morestoryline", False),
        debug=kwargs.get("debug", False),
    )
    return _search_adult(number, sources, ctx)


def get_supported_sources(tag: str = "adult") -> str:
    if tag == "adult":
        return ",".join(ADULT_SOURCES)
    return ",".join(GENERAL_SOURCES)


def _load_parser(source: str) -> Parser:
    """Dynamically load a scraper module and return its parser instance."""
    module = importlib.import_module("." + source, "mdc.scrapers")
    parser_type = getattr(module, source.capitalize())
    return parser_type()


def _search_adult(number: str, sources: str | list | None, ctx: SearchContext) -> MovieData | None:
    if ctx.specifiedSource:
        source_list = [ctx.specifiedSource]
    elif isinstance(sources, list):
        source_list = sources
    else:
        source_list = _check_adult_sources(sources, number)

    result = MovieData()
    for source in source_list:
        try:
            if ctx.debug:
                logger.info("Trying source: %s", source)
            try:
                parser = _load_parser(source)
                data = parser.scrape(number, ctx)
                if data == 404:
                    continue
                if not isinstance(data, MovieData):
                    continue
                result = data
            except Exception as e:
                logger.debug("Source %s error: %s", source, e)
                continue

            if _is_valid(result):
                if ctx.debug:
                    logger.info("Found [%s] on '%s'", number, source)
                break
        except Exception:
            continue

    # javdb covers have watermarks - try to get cover from another source
    if result.source == "javdb":
        try:
            other_sources = source_list[source_list.index("javdb") + 1:]
            other = _search_adult(number, other_sources, ctx)
            if other and other.cover:
                result.cover = other.cover
                if ctx.debug:
                    logger.info("Using cover from '%s' instead of javdb", other.source)
        except Exception:
            pass

    if not result or not result.title:
        return None

    # Fill anonymous actor
    if not result.actor:
        from mdc.config import getInstance
        conf = getInstance()
        if conf.anonymous_fill():
            target_lang = conf.get_target_language()
            if "zh_" in target_lang or "ZH" in target_lang:
                result.actor = "佚名"
            else:
                result.actor = "Anonymous"

    # When source is javbus, replace cover with DMM high-res version
    if result.source == "javbus" and result.extrafanart:
        cover_url = result.extrafanart[0]
        if cover_url.endswith("jp-1.jpg"):
            result.cover = cover_url.replace("jp-1.jpg", "pl.jpg")

    return result


def _check_adult_sources(c_sources: str | None, file_number: str) -> list[str]:
    if not c_sources:
        sources = list(ADULT_SOURCES)
    else:
        sources = c_sources.split(",")

    def insert_front(src_list, source):
        if source in src_list:
            src_list.insert(0, src_list.pop(src_list.index(source)))
        return src_list

    if len(sources) <= len(ADULT_SOURCES):
        lo = file_number.lower()
        if "carib" in sources:
            sources = insert_front(sources, "caribpr")
            sources = insert_front(sources, "carib")
        elif "item" in file_number or "GETCHU" in file_number.upper():
            sources = ["getchu"]
        elif "rj" in lo or "vj" in lo:
            sources = ["dlsite"]
        elif re.search(r"[\u3040-\u309F\u30A0-\u30FF]+", file_number):
            sources = ["dlsite", "getchu"]
        elif "pcolle" in sources and "pcolle" in lo:
            sources = ["pcolle"]
        elif "fc2" in lo:
            sources = ["fc2", "avsox", "msin"]
        elif re.search(r"\d+\D+-", file_number) or "siro" in lo:
            if "mgstage" in sources:
                sources = insert_front(sources, "mgstage")
        elif "gcolle" in sources and re.search(r"\d{6}", file_number):
            sources = insert_front(sources, "gcolle")
        elif (
            re.search(r"^\d{5,}", file_number)
            or re.search(r"^\d{6}-\d{3}", file_number)
            or "heyzo" in lo
        ):
            sources = ["avsox", "carib", "caribpr", "javbus", "xcity", "javdb"]
        elif re.search(r"^[a-z0-9]{3,}$", lo):
            if "xcity" in sources:
                sources = insert_front(sources, "xcity")
            if "madou" in sources:
                sources = insert_front(sources, "madou")

    # Remove unknown sources
    valid = set(ADULT_SOURCES)
    return [s for s in sources if s in valid]


def _is_valid(data: MovieData) -> bool:
    if not data.title or data.title == "null":
        return False
    if not data.number or data.number == "null":
        return False
    if (not data.cover or data.cover == "null") and (
        not data.cover_small or data.cover_small == "null"
    ):
        return False
    return True
