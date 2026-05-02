# -*- coding: utf-8 -*-

"""Fanza (DMM) scraper using the video.dmm.co.jp GraphQL API."""

import logging
import re
from urllib.parse import parse_qs, urlparse

import requests

from mdc.models import MovieData
from mdc.scrapers.base import Parser

logger = logging.getLogger(__name__)

GRAPHQL_ENDPOINT = "https://api.video.dmm.co.jp/graphql"
PAGE_BASE_URL = "https://video.dmm.co.jp/av/content/?id="
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/100.0.4896.133 Safari/537.36"
)

CONTENT_QUERY = """
query ContentPageData($id: ID!) {
  ppvContent(id: $id) {
    id
    floor
    title
    description
    isExclusiveDelivery
    releaseStatus
    packageImage {
      largeUrl
      mediumUrl
    }
    sampleImages {
      number
      imageUrl
      largeImageUrl
    }
    sample2DMovie {
      highestMovieUrl
      hlsMovieUrl
    }
    deliveryStartDate
    makerReleasedAt
    duration
    actresses {
      id
      name
      nameRuby
      imageUrl
    }
    histrions {
      id
      name
    }
    directors {
      id
      name
    }
    series {
      id
      name
    }
    maker {
      id
      name
    }
    label {
      id
      name
    }
    genres {
      id
      name
    }
    contentType
    makerContentId
  }
  reviewSummary(contentId: $id) {
    average
    total
  }
}
"""


class Fanza(Parser):
    source = "fanza"

    def extraInit(self):
        # makerContentId can differ from the input number (e.g. xvsr00876 -> XVSR-876)
        self.allow_number_change = True

    def search(self, number: str):
        self.number = number
        candidates = self._build_candidate_ids(number)
        for cid in candidates:
            payload = self._fetch_content(cid)
            if payload is None:
                continue
            self.detailurl = PAGE_BASE_URL + cid
            return self._build_movie(payload)
        return 404

    def _build_candidate_ids(self, number: str) -> list[str]:
        """Build a list of CID candidates to try against the GraphQL API."""
        candidates: list[str] = []

        # If specifiedUrl provided, extract id from it first
        if self.specifiedUrl:
            cid = self._extract_cid_from_url(self.specifiedUrl)
            if cid:
                candidates.append(cid)

        cleaned = number.strip().lower()
        cleaned = cleaned.rstrip(".")
        # h-xxx → h_xxx (legacy fanza prefix uses underscore)
        if cleaned.startswith("h-"):
            cleaned = "h_" + cleaned[2:]

        # Strip everything except letters, digits, and underscore
        normalized = re.sub(r"[^0-9a-z_]", "", cleaned)
        if normalized and normalized not in candidates:
            candidates.append(normalized)

        # Try splitting into letter prefix + number, padding number to 5 digits
        match = re.match(r"^([a-z][a-z0-9_]*?)(\d+)$", normalized)
        if match:
            prefix, num = match.group(1), match.group(2)
            for width in (5, 4, 3):
                if len(num) < width:
                    padded = prefix + num.zfill(width)
                    if padded not in candidates:
                        candidates.append(padded)
            # Also try without padding in case the cid has fewer digits
            stripped = prefix + num.lstrip("0")
            if stripped and stripped not in candidates:
                candidates.append(stripped)

        return candidates

    @staticmethod
    def _extract_cid_from_url(url: str) -> str:
        """Extract the CID from a Fanza/DMM URL of either format."""
        try:
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            if "id" in qs and qs["id"]:
                return qs["id"][0].lower()
            if "cid" in qs and qs["cid"]:
                return qs["cid"][0].lower()
            # Legacy /=/cid=... path style
            m = re.search(r"cid=([0-9a-zA-Z_]+)", url)
            if m:
                return m.group(1).lower()
        except Exception:
            pass
        return ""

    def _fetch_content(self, cid: str) -> dict | None:
        headers = {
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Origin": "https://video.dmm.co.jp",
            "Referer": PAGE_BASE_URL + cid,
        }
        if self.extraheader:
            headers.update(self.extraheader)
        cookies = {"age_check_done": "1"}
        if isinstance(self.cookies, dict):
            cookies.update(self.cookies)

        try:
            resp = requests.post(
                GRAPHQL_ENDPOINT,
                json={"query": CONTENT_QUERY, "variables": {"id": cid}},
                headers=headers,
                cookies=cookies,
                proxies=self.proxies,
                verify=self.verify if self.verify is not None else True,
                timeout=20,
            )
        except Exception as e:
            logger.debug("fanza GraphQL request failed for %s: %s", cid, e)
            return None

        if resp.status_code != 200:
            logger.debug("fanza GraphQL %s returned status %d", cid, resp.status_code)
            return None
        try:
            data = resp.json()
        except Exception as e:
            logger.debug("fanza GraphQL %s invalid JSON: %s", cid, e)
            return None

        content = (data.get("data") or {}).get("ppvContent")
        if not content:
            return None
        return data["data"]

    def _build_movie(self, payload: dict) -> MovieData:
        content = payload["ppvContent"]
        review = payload.get("reviewSummary") or {}

        number = content.get("makerContentId") or content.get("id") or self.number

        actresses = content.get("actresses") or []
        actor_list = [a["name"] for a in actresses if a.get("name")]
        actor_photo = {a["name"]: a.get("imageUrl") or "" for a in actresses if a.get("name")}

        directors = content.get("directors") or []
        director = directors[0]["name"] if directors and directors[0].get("name") else ""

        genres = content.get("genres") or []
        tags = [g["name"] for g in genres if g.get("name")]

        package = content.get("packageImage") or {}
        cover = package.get("largeUrl") or package.get("mediumUrl") or ""
        cover_small = package.get("mediumUrl") or ""

        sample_images = content.get("sampleImages") or []
        extrafanart = [
            s.get("largeImageUrl") or s.get("imageUrl")
            for s in sample_images
            if s.get("largeImageUrl") or s.get("imageUrl")
        ]

        sample_movie = content.get("sample2DMovie") or {}
        trailer = sample_movie.get("highestMovieUrl") or sample_movie.get("hlsMovieUrl") or ""

        release = self._format_release(
            content.get("makerReleasedAt") or content.get("deliveryStartDate")
        )
        year = release[:4] if release else ""

        duration = content.get("duration")
        runtime = str(duration // 60) if isinstance(duration, int) and duration else ""

        maker = content.get("maker") or {}
        studio = maker.get("name") or ""

        label_obj = content.get("label") or {}
        label = label_obj.get("name") or ""

        series_obj = content.get("series") or {}
        series = series_obj.get("name") or ""

        rating = review.get("average")
        votes = review.get("total")

        return MovieData(
            number=number,
            title=content.get("title") or "",
            studio=studio,
            release=release,
            year=year,
            outline=content.get("description") or "",
            runtime=runtime,
            director=director,
            actor=", ".join(actor_list),
            actor_list=actor_list,
            actor_photo=actor_photo,
            cover=cover,
            cover_small=cover_small,
            extrafanart=extrafanart,
            trailer=trailer,
            tag=tags,
            label=label,
            series=series,
            userrating=float(rating) if isinstance(rating, (int, float)) else "",
            uservotes=int(votes) if isinstance(votes, int) else "",
            uncensored=False,
            website=self.detailurl,
            source=self.source,
            imagecut=1,
            allow_number_change=self.allow_number_change,
        )

    @staticmethod
    def _format_release(value) -> str:
        if not value or not isinstance(value, str):
            return ""
        # Inputs look like "2026-05-04T15:00:00Z"
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        return ""
