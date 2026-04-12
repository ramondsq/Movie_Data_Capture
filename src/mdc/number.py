"""Extract movie number from filename."""

import os
import re

_SITE_PATTERN = re.compile(
    r"^\w+\.(cc|com|net|me|club|jp|tv|xyz|biz|wiki|info|tw|us|de)@|^22-sht\.me|"
    r"^(fhd|hd|sd|1080p|720p|4K)(-|_)|"
    r"(-|_)(fhd|hd|sd|1080p|720p|4K|x264|x265|uncensored|hack|leak)",
    re.IGNORECASE,
)

# Rules mapping filename patterns to number extraction lambdas (javdb naming conventions)
_TAKE_NUM_RULES = {
    "tokyo.*hot": lambda x: str(
        re.search(r"(cz|gedo|k|n|red-|se)\d{2,4}", x, re.I).group()
    ),
    "carib": lambda x: str(
        re.search(r"\d{6}(-|_)\d{3}", x, re.I).group()
    ).replace("_", "-"),
    "1pon|mura|paco": lambda x: str(
        re.search(r"\d{6}(-|_)\d{3}", x, re.I).group()
    ).replace("-", "_"),
    "10mu": lambda x: str(
        re.search(r"\d{6}(-|_)\d{2}", x, re.I).group()
    ).replace("-", "_"),
    "x-art": lambda x: str(
        re.search(r"x-art\.\d{2}\.\d{2}\.\d{2}", x, re.I).group()
    ),
    "xxx-av": lambda x: "".join(
        ["xxx-av-", re.findall(r"xxx-av[^\d]*(\d{3,5})[^\d]*", x, re.I)[0]]
    ),
    "heydouga": lambda x: "heydouga-"
    + "-".join(re.findall(r"(\d{4})[\-_](\d{3,4})[^\d]*", x, re.I)[0]),
    "heyzo": lambda x: "HEYZO-"
    + re.findall(r"heyzo[^\d]*(\d{4})", x, re.I)[0],
    "mdbk": lambda x: str(re.search(r"mdbk(-|_)(\d{4})", x, re.I).group()),
    "mdtm": lambda x: str(re.search(r"mdtm(-|_)(\d{4})", x, re.I).group()),
    "caribpr": lambda x: str(
        re.search(r"\d{6}(-|_)\d{3}", x, re.I).group()
    ).replace("_", "-"),
}


def _get_number_by_dict(filename: str) -> str | None:
    try:
        for k, v in _TAKE_NUM_RULES.items():
            if re.search(k, filename, re.I):
                return v(filename)
    except Exception:
        pass
    return None


def get_number(debug: bool, file_path: str) -> str | None:
    """Extract movie number from a file path.

    >>> get_number(False, "/path/to/snis-829.mp4")
    'snis-829'
    >>> get_number(False, "/path/to/snis-829-C.mp4")
    'snis-829'
    """
    filepath = os.path.basename(file_path)
    try:
        # Try custom regex patterns from config
        try:
            from mdc.config import getInstance
            custom_regexs = getInstance().number_regexs()
            if custom_regexs.split():
                for regex in custom_regexs.split():
                    try:
                        m = re.search(regex, filepath)
                        if m:
                            return m.group()
                    except Exception as e:
                        print(f"[-]custom regex exception: {e} [{regex}]")
        except Exception:
            pass

        # Try dict-based rules
        file_number = _get_number_by_dict(filepath)
        if file_number:
            return file_number

        # Subtitle group pattern
        if "字幕组" in filepath or "SUB" in filepath.upper() or re.match(r"[\u30a0-\u30ff]+", filepath):
            filepath = _SITE_PATTERN.sub("", filepath)
            filepath = re.sub(r"\[.*?\]", "", filepath)
            filepath = filepath.replace(".chs", "").replace(".cht", "")
            file_number = str(re.findall(r"(.+?)\.", filepath)).strip(" [']")
            return file_number

        # Standard number with dash or underscore
        if "-" in filepath or "_" in filepath:
            filepath = _SITE_PATTERN.sub("", filepath)
            filename = str(re.sub(r"\[\d{4}-\d{1,2}-\d{1,2}\] - ", "", filepath))
            lower_check = filename.lower()
            if "fc2" in lower_check:
                filename = lower_check.replace("--", "-").replace("_", "-").upper()
            filename = re.sub("[-_]cd\\d{1,2}", "", filename, flags=re.IGNORECASE)
            if not re.search("-|_", filename):
                return str(re.search(r"\w+", filename[: filename.find(".")], re.A).group())
            file_number = os.path.splitext(filename)
            m = re.search(r"[\w\-_]+", filename, re.A)
            if m:
                file_number = str(m.group())
            else:
                file_number = file_number[0]

            new_file_number = file_number
            if re.search("-c", file_number, flags=re.IGNORECASE):
                new_file_number = re.sub("(-|_)c$", "", file_number, flags=re.IGNORECASE)
            elif re.search("-u$", file_number, flags=re.IGNORECASE):
                new_file_number = re.sub("(-|_)u$", "", file_number, flags=re.IGNORECASE)
            elif re.search("-uc$", file_number, flags=re.IGNORECASE):
                new_file_number = re.sub("(-|_)uc$", "", file_number, flags=re.IGNORECASE)
            elif re.search(r"\d+ch$", file_number, flags=re.I):
                new_file_number = file_number[:-2]

            return new_file_number.upper()

        # No dash/underscore - FANZA CID or other formats
        oumei = re.search(r"[a-zA-Z]+\.\d{2}\.\d{2}\.\d{2}", filepath)
        if oumei:
            return oumei.group()
        try:
            return (
                str(
                    re.findall(
                        r"(.+?)\.",
                        str(re.search(r'([^<>/\\\\|:""\\*\\?]+)\\.\\w+$', filepath).group()),
                    )
                )
                .strip("['']")
                .replace("_", "-")
            )
        except Exception:
            return str(re.search(r"(.+?)\.", filepath)[0])
    except Exception as e:
        if debug:
            print(f"[-]Number Parser exception: {e} [{file_path}]")
        return None


class _UncensoredCache:
    def __init__(self):
        self._prefix = None

    def set(self, v: list):
        if not v or not v[0]:
            raise ValueError("input prefix list empty or None")
        s = v[0]
        if len(v) > 1:
            for i in v[1:]:
                s += f"|{i}.+"
        self._prefix = re.compile(s, re.I)

    def check(self, number) -> bool:
        if self._prefix is None:
            raise ValueError("No init re compile")
        return bool(self._prefix.match(number))

    @property
    def is_empty(self) -> bool:
        return self._prefix is None


_uncensored_cache = _UncensoredCache()


def is_uncensored(number: str) -> bool:
    if re.match(
        r"[\d-]{4,}|\d{6}_\d{2,3}|(cz|gedo|k|n|red-|se)\d{2,4}|heyzo.+|xxx-av-.+|heydouga-.+|x-art\.\d{2}\.\d{2}\.\d{2}",
        number,
        re.I,
    ):
        return True
    if _uncensored_cache.is_empty:
        from mdc.config import getInstance
        _uncensored_cache.set(getInstance().get_uncensored().split(","))
    return _uncensored_cache.check(number)
