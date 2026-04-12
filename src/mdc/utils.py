import json
import os
import re
import time
from pathlib import Path
from unicodedata import category


def file_modification_days(filename: str) -> int:
    mfile = Path(filename)
    if not mfile.is_file():
        return 9999
    mtime = int(mfile.stat().st_mtime)
    now = int(time.time())
    days = int((now - mtime) / (24 * 60 * 60))
    return days if days >= 0 else 9999


def file_not_exist_or_empty(filepath) -> bool:
    return not os.path.isfile(filepath) or os.path.getsize(filepath) == 0


def is_japanese(raw: str) -> bool:
    return bool(re.search(r"[\u3040-\u309F\u30A0-\u30FF\uFF66-\uFF9F]", raw, re.UNICODE))


def cn_space(v: str, n: int) -> int:
    """Calculate space padding width accounting for CJK characters."""
    return n - [category(c) for c in v].count("Lo")


def special_characters_replacement(text) -> str:
    """Replace filesystem-unsafe characters with unicode look-alikes."""
    if not isinstance(text, str):
        return text
    return (
        text.replace("\\", "\u2216")  # SET MINUS
        .replace("/", "\u2215")  # DIVISION SLASH
        .replace(":", "\ua789")  # MODIFIER LETTER COLON
        .replace("*", "\u2217")  # ASTERISK OPERATOR
        .replace("?", "\uff1f")  # FULLWIDTH QUESTION MARK
        .replace('"', "\uff02")  # FULLWIDTH QUOTATION MARK
        .replace("<", "\u1438")  # CANADIAN SYLLABICS PA
        .replace(">", "\u1433")  # CANADIAN SYLLABICS PO
        .replace("|", "\u01c0")  # LATIN LETTER DENTAL CLICK
        .replace("&lsquo;", "\u2018")
        .replace("&rsquo;", "\u2019")
        .replace("&hellip;", "\u2026")
        .replace("&amp;", "\uff06")
        .replace("&", "\uff06")
    )


def load_cookies(cookie_json_filename: str) -> tuple:
    """Load cookies from a JSON file. Returns (dict, filepath) or (None, None)."""
    filename = os.path.basename(cookie_json_filename)
    if not filename:
        return None, None
    path_search_order = (
        Path.cwd() / filename,
        Path.home() / filename,
        Path.home() / f".mdc/{filename}",
        Path.home() / f".local/share/mdc/{filename}",
    )
    try:
        for p in path_search_order:
            if p.is_file():
                return json.loads(p.read_text(encoding="utf-8")), str(p.resolve())
    except Exception:
        pass
    return None, None


def delete_all_elements_in_list(string: str, lists: list) -> list:
    return [i for i in lists if i != string]


def delete_all_elements_in_str(string_delete: str, string: str) -> str:
    for i in string:
        if i == string_delete:
            string = string.replace(i, "")
    return string
