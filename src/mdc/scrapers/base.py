# -*- coding: utf-8 -*-

"""Base parser class for all scrapers."""

from __future__ import annotations

import logging
import re

from lxml import etree
from lxml.html import HtmlElement

from mdc.models import MovieData

logger = logging.getLogger(__name__)


def getTreeElement(tree: HtmlElement, expr: str = "", index: int = 0) -> str:
    if not expr:
        return ""
    result = tree.xpath(expr)
    try:
        return result[index]
    except Exception:
        return ""


def getTreeAll(tree: HtmlElement, expr: str = "") -> list:
    if not expr:
        return []
    return tree.xpath(expr) or []


class Parser:
    """Base scraper class with XPath-based extraction."""

    source = "base"
    # xpath expressions - subclasses override these
    expr_number = ""
    expr_title = ""
    expr_studio = ""
    expr_studio2 = ""
    expr_runtime = ""
    expr_runtime2 = ""
    expr_release = ""
    expr_outline = ""
    expr_director = ""
    expr_actor = ""
    expr_tags = ""
    expr_label = ""
    expr_label2 = ""
    expr_series = ""
    expr_series2 = ""
    expr_cover = ""
    expr_cover2 = ""
    expr_smallcover = ""
    expr_extrafanart = ""
    expr_trailer = ""
    expr_actorphoto = ""
    expr_uncensored = ""
    expr_userrating = ""
    expr_uservotes = ""

    def init(self):
        self.imagecut = 1
        self.uncensored = False
        self.allow_number_change = False
        self.proxies = None
        self.verify = None
        self.extraheader = None
        self.cookies = None
        self.morestoryline = False
        self.specifiedUrl = None
        self.extraInit()

    def extraInit(self):
        pass

    def scrape(self, number: str, core=None) -> MovieData | int:
        """Scrape metadata for the given number."""
        self.init()
        self.updateCore(core)
        result = self.search(number)
        return result

    def search(self, number: str) -> MovieData | int:
        self.number = number
        if self.specifiedUrl:
            self.detailurl = self.specifiedUrl
        else:
            self.detailurl = self.queryNumberUrl(number)
        if not self.detailurl:
            return 404
        htmltree = self.getHtmlTree(self.detailurl)
        if htmltree == 404:
            return 404
        result = self.dictformat(htmltree)
        return result

    def updateCore(self, core):
        if not core:
            return
        if core.proxies:
            self.proxies = core.proxies
        if core.verify:
            self.verify = core.verify
        # storyline is now fetched separately in the pipeline, not during scraping
        if core.specifiedSource == self.source:
            self.specifiedUrl = core.specifiedUrl

    def queryNumberUrl(self, number: str) -> str:
        return "http://detailurl.ai/" + number

    def getHtml(self, url: str, type=None) -> str | int:
        from mdc.scrapers import httprequest
        resp = httprequest.get(
            url,
            cookies=self.cookies,
            proxies=self.proxies,
            extra_headers=self.extraheader,
            verify=self.verify,
            return_type=type,
        )
        if (
            "<title>404 Page Not Found" in resp
            or "<title>未找到页面" in resp
            or "404 Not Found" in resp
            or "<title>404" in resp
            or "<title>お探しの商品が見つかりません" in resp
        ):
            return 404
        return resp

    def getHtmlTree(self, url: str, type=None):
        resp = self.getHtml(url, type)
        if resp == 404:
            return 404
        return etree.fromstring(resp, etree.HTMLParser())

    def dictformat(self, htmltree) -> MovieData:
        try:
            movie = MovieData(
                number=self.getNum(htmltree),
                title=self.getTitle(htmltree),
                studio=self.getStudio(htmltree),
                release=self.getRelease(htmltree),
                year=self.getYear(htmltree),
                outline=self.getOutline(htmltree),
                runtime=self.getRuntime(htmltree),
                director=self.getDirector(htmltree),
                actor=", ".join(self.getActors(htmltree)) if isinstance(self.getActors(htmltree), list) else self.getActors(htmltree),
                actor_list=self.getActors(htmltree) if isinstance(self.getActors(htmltree), list) else [],
                actor_photo=self.getActorPhoto(htmltree),
                cover=self.getCover(htmltree),
                cover_small=self.getSmallCover(htmltree),
                extrafanart=self.getExtrafanart(htmltree),
                trailer=self.getTrailer(htmltree),
                tag=self.getTags(htmltree),
                label=self.getLabel(htmltree),
                series=self.getSeries(htmltree),
                userrating=self.getUserRating(htmltree),
                uservotes=self.getUserVotes(htmltree),
                uncensored=self.getUncensored(htmltree),
                website=self.detailurl,
                source=self.source,
                imagecut=self.getImagecut(htmltree),
                allow_number_change=self.allow_number_change,
            )
            movie = self.extradict(movie)
        except Exception as e:
            logger.debug("dictformat error: %s", e)
            movie = MovieData(title="")
        return movie

    def extradict(self, movie: MovieData) -> MovieData:
        return movie

    def getNum(self, htmltree):
        return self.getTreeElement(htmltree, self.expr_number)

    def getTitle(self, htmltree):
        return self.getTreeElement(htmltree, self.expr_title).strip()

    def getRelease(self, htmltree):
        return self.getTreeElement(htmltree, self.expr_release).strip().replace("/", "-")

    def getYear(self, htmltree):
        try:
            release = self.getRelease(htmltree)
            return str(re.findall(r"\d{4}", release)).strip(" ['']")
        except Exception:
            return ""

    def getRuntime(self, htmltree):
        return (
            self.getTreeElementbyExprs(htmltree, self.expr_runtime, self.expr_runtime2)
            .strip()
            .rstrip("mi")
        )

    def getOutline(self, htmltree):
        return self.getTreeElement(htmltree, self.expr_outline).strip()

    def getDirector(self, htmltree):
        return self.getTreeElement(htmltree, self.expr_director).strip()

    def getActors(self, htmltree) -> list:
        return self.getTreeAll(htmltree, self.expr_actor)

    def getTags(self, htmltree) -> list:
        alls = self.getTreeAll(htmltree, self.expr_tags)
        tags = []
        for t in alls:
            for tag in t.strip().split(","):
                tag = tag.strip()
                if tag:
                    tags.append(tag)
        return tags

    def getStudio(self, htmltree):
        return self.getTreeElementbyExprs(htmltree, self.expr_studio, self.expr_studio2)

    def getLabel(self, htmltree):
        return self.getTreeElementbyExprs(htmltree, self.expr_label, self.expr_label2)

    def getSeries(self, htmltree):
        return self.getTreeElementbyExprs(htmltree, self.expr_series, self.expr_series2)

    def getCover(self, htmltree):
        return self.getTreeElementbyExprs(htmltree, self.expr_cover, self.expr_cover2)

    def getSmallCover(self, htmltree):
        return self.getTreeElement(htmltree, self.expr_smallcover)

    def getExtrafanart(self, htmltree) -> list:
        return self.getTreeAll(htmltree, self.expr_extrafanart)

    def getTrailer(self, htmltree):
        return self.getTreeElement(htmltree, self.expr_trailer)

    def getActorPhoto(self, htmltree) -> dict:
        return {}

    def getUncensored(self, htmltree) -> bool:
        if self.uncensored:
            return self.uncensored
        tags = [x.lower() for x in self.getTags(htmltree) if len(x)]
        title = self.getTitle(htmltree)
        if self.expr_uncensored:
            u = self.getTreeAll(htmltree, self.expr_uncensored)
            self.uncensored = bool(u)
        elif "無码" in tags or "無修正" in tags or "uncensored" in tags or "无码" in tags:
            self.uncensored = True
        elif "無码" in title or "無修正" in title or "uncensored" in title.lower():
            self.uncensored = True
        return self.uncensored

    def getImagecut(self, htmltree):
        return self.imagecut

    def getUserRating(self, htmltree):
        numstrs = self.getTreeElement(htmltree, self.expr_userrating)
        nums = re.findall("[0-9.]+", numstrs)
        if len(nums) == 1:
            return float(nums[0])
        return ""

    def getUserVotes(self, htmltree):
        votestrs = self.getTreeElement(htmltree, self.expr_uservotes)
        votes = re.findall("[0-9]+", votestrs)
        if len(votes) == 1:
            return int(votes[0])
        return ""

    def getTreeElement(self, tree, expr, index=0):
        return getTreeElement(tree, expr, index)

    def getTreeAll(self, tree, expr):
        return getTreeAll(tree, expr)

    def getTreeElementbyExprs(self, tree, expr, expr2=""):
        try:
            first = self.getTreeElement(tree, expr).strip()
            if first:
                return first
            second = self.getTreeElement(tree, expr2).strip()
            if second:
                return second
            return ""
        except Exception:
            return ""

    def getTreeAllbyExprs(self, tree, expr, expr2=""):
        try:
            result1 = self.getTreeAll(tree, expr)
            result2 = self.getTreeAll(tree, expr2)
            clean = [x.strip() for x in result1 if x.strip() and x.strip() != ","]
            clean2 = [x.strip() for x in result2 if x.strip() and x.strip() != ","]
            return list(set(clean + clean2))
        except Exception:
            return []
