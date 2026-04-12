import configparser
import os
import re
import sys
from pathlib import Path

from mdc.models import ProxyConfig

_instance: "Config | None" = None


def getInstance() -> "Config":
    global _instance
    if _instance is None:
        _instance = Config()
    return _instance


class ConfigError(SystemExit):
    pass


class Config:
    def __init__(self, path: str = "config.ini"):
        global _instance

        path_search_order = (
            Path(path),
            Path.cwd() / "config.ini",
            Path.home() / "mdc.ini",
            Path.home() / ".mdc.ini",
            Path.home() / ".mdc/config.ini",
            Path.home() / ".config/mdc/config.ini",
        )
        ini_path = None
        for p in path_search_order:
            if p.is_file():
                ini_path = p.resolve()
                break

        if not ini_path:
            # Try script directory
            script_dir = Path(__file__).resolve().parent.parent.parent
            candidate = script_dir / "config.ini"
            if candidate.is_file():
                ini_path = candidate.resolve()

        if not ini_path:
            print("ERROR: Config file not found!")
            print("Please put config file into one of the following paths:")
            print("\n".join(str(p.resolve()) for p in path_search_order[2:]))
            raise ConfigError(2)

        self.conf = configparser.ConfigParser()
        self.ini_path = ini_path
        try:
            if not self.conf.read(ini_path, encoding="utf-8-sig"):
                self.conf.read(ini_path, encoding="utf-8")
        except UnicodeDecodeError:
            self.conf.read(ini_path, encoding="utf-8")
        except Exception as e:
            print(f"ERROR: Cannot read config file: {e}")
            raise ConfigError(-1)

        if _instance is None:
            _instance = self

    def set_override(self, option_cmd: str):
        sections = self.conf.sections()
        sec_name = None
        for cmd in option_cmd.split(";"):
            syntax_err = True
            rex = re.findall(r"^(.*?):(.*?)(=|\+=)(.*)$", cmd, re.U)
            if len(rex) and len(rex[0]) == 4:
                (sec, key, assign, val) = rex[0]
                sec_lo = sec.lower().strip()
                key_lo = key.lower().strip()
                syntax_err = False
            elif sec_name:
                rex = re.findall(r"^(.*?)(=|\+=)(.*)$", cmd, re.U)
                if len(rex) and len(rex[0]) == 3:
                    (key, assign, val) = rex[0]
                    sec_lo = sec_name.lower()
                    key_lo = key.lower().strip()
                    syntax_err = False
            if syntax_err:
                raise ConfigError(
                    f"Config override syntax incorrect: '{cmd}' in '{option_cmd}'"
                )
            if not sec_lo:
                raise ConfigError(f"Config override section name empty: '{cmd}'")
            if not key_lo:
                raise ConfigError(f"Config override key name empty: '{cmd}'")

            sec_name = None
            for s in sections:
                if s.lower().startswith(sec_lo):
                    if sec_name:
                        raise ConfigError(
                            f"Config override section '{sec_lo}' is ambiguous: "
                            f"'{sec_name}' vs '{s}'"
                        )
                    sec_name = s
            if sec_name is None:
                raise ConfigError(f"Config override section '{sec}' not found: '{cmd}'")

            key_name = None
            keys = self.conf[sec_name]
            for k in keys:
                if k.lower().startswith(key_lo):
                    if key_name:
                        raise ConfigError(
                            f"Config override key '{key_lo}' is ambiguous: "
                            f"'{key_name}' vs '{k}'"
                        )
                    key_name = k
            if key_name is None:
                raise ConfigError(f"Config override key '{key}' not found: '{cmd}'")

            if assign == "+=":
                val = keys[key_name] + val
            self.conf.set(sec_name, key_name, val)

    # ---- common section ----

    def main_mode(self) -> int:
        return self.conf.getint("common", "main_mode")

    def source_folder(self) -> str:
        return self.conf.get("common", "source_folder").replace("\\\\", "/").replace("\\", "/")

    def failed_folder(self) -> str:
        return self.conf.get("common", "failed_output_folder").replace("\\\\", "/").replace("\\", "/")

    def success_folder(self) -> str:
        return self.conf.get("common", "success_output_folder").replace("\\\\", "/").replace("\\", "/")

    def actor_gender(self) -> str:
        return self.conf.get("common", "actor_gender")

    def link_mode(self) -> int:
        return self.conf.getint("common", "link_mode")

    def scan_hardlink(self) -> bool:
        return self.conf.getboolean("common", "scan_hardlink", fallback=False)

    def failed_move(self) -> bool:
        return self.conf.getboolean("common", "failed_move")

    def auto_exit(self) -> bool:
        return self.conf.getboolean("common", "auto_exit")

    def translate_to_sc(self) -> bool:
        return self.conf.getboolean("common", "translate_to_sc")

    def multi_threading(self) -> bool:
        return self.conf.getboolean("common", "multi_threading")

    def del_empty_folder(self) -> bool:
        return self.conf.getboolean("common", "del_empty_folder")

    def nfo_skip_days(self) -> int:
        return self.conf.getint("common", "nfo_skip_days", fallback=30)

    def ignore_failed_list(self) -> bool:
        return self.conf.getboolean("common", "ignore_failed_list")

    def download_only_missing_images(self) -> bool:
        return self.conf.getboolean("common", "download_only_missing_images")

    def mapping_table_validity(self) -> int:
        return self.conf.getint("common", "mapping_table_validity")

    def jellyfin(self) -> int:
        return self.conf.getint("common", "jellyfin")

    def actor_only_tag(self) -> bool:
        return self.conf.getboolean("common", "actor_only_tag")

    def sleep(self) -> int:
        return self.conf.getint("common", "sleep")

    def anonymous_fill(self) -> bool:
        return self.conf.getint("common", "anonymous_fill")

    # ---- advenced_sleep section ----

    def stop_counter(self) -> int:
        return self.conf.getint("advenced_sleep", "stop_counter", fallback=0)

    def rerun_delay(self) -> int:
        value = self.conf.get("advenced_sleep", "rerun_delay")
        if not (isinstance(value, str) and re.match(r"^[\dsmh]+$", value, re.I)):
            return 0
        if value.isnumeric() and int(value) >= 0:
            return int(value)
        sec = 0
        sec += sum(int(v) for v in re.findall(r"(\d+)s", value, re.I))
        sec += sum(int(v) for v in re.findall(r"(\d+)m", value, re.I)) * 60
        sec += sum(int(v) for v in re.findall(r"(\d+)h", value, re.I)) * 3600
        return sec

    # ---- translate section ----

    def is_translate(self) -> bool:
        return self.conf.getboolean("translate", "switch")

    def get_translate_engine(self) -> str:
        return self.conf.get("translate", "engine")

    def get_target_language(self) -> str:
        return self.conf.get("translate", "target_language")

    def get_translate_key(self) -> str:
        return self.conf.get("translate", "key")

    def get_translate_delay(self) -> int:
        return self.conf.getint("translate", "delay")

    def translate_values(self) -> str:
        return self.conf.get("translate", "values")

    def get_translate_service_site(self) -> str:
        return self.conf.get("translate", "service_site")

    # ---- trailer section ----

    def is_trailer(self) -> bool:
        return self.conf.getboolean("trailer", "switch")

    # ---- watermark section ----

    def is_watermark(self) -> bool:
        return self.conf.getboolean("watermark", "switch")

    def watermark_type(self) -> int:
        return int(self.conf.get("watermark", "water"))

    # ---- extrafanart section ----

    def is_extrafanart(self) -> bool:
        return self.conf.getboolean("extrafanart", "switch")

    def extrafanart_thread_pool_download(self) -> int:
        try:
            v = self.conf.getint("extrafanart", "parallel_download")
            return v if v >= 0 else 5
        except Exception:
            return 5

    def get_extrafanart(self) -> str:
        return self.conf.get("extrafanart", "extrafanart_folder", fallback="extrafanart")

    # ---- proxy section ----

    def proxy(self) -> ProxyConfig:
        sec = "proxy"
        switch = self.conf.get(sec, "switch")
        return ProxyConfig(
            enable=switch in ("1", 1),
            address=self.conf.get(sec, "proxy"),
            timeout=self.conf.getint(sec, "timeout"),
            retry=self.conf.getint(sec, "retry"),
            proxytype=self.conf.get(sec, "type"),
        )

    def cacert_file(self) -> str:
        return self.conf.get("proxy", "cacert_file")

    # ---- media section ----

    def media_type(self) -> str:
        return self.conf.get("media", "media_type")

    def sub_rule(self) -> set[str]:
        return set(self.conf.get("media", "sub_type").lower().split(","))

    # ---- Name_Rule section ----

    def naming_rule(self) -> str:
        return self.conf.get("Name_Rule", "naming_rule")

    def location_rule(self) -> str:
        return self.conf.get("Name_Rule", "location_rule")

    def max_title_len(self) -> int:
        try:
            return self.conf.getint("Name_Rule", "max_title_len")
        except Exception:
            return 50

    def image_naming_with_number(self) -> bool:
        try:
            return self.conf.getboolean("Name_Rule", "image_naming_with_number")
        except Exception:
            return False

    def number_uppercase(self) -> bool:
        try:
            return self.conf.getboolean("Name_Rule", "number_uppercase")
        except Exception:
            return False

    def number_regexs(self) -> str:
        try:
            return self.conf.get("Name_Rule", "number_regexs")
        except Exception:
            return ""

    # ---- priority section ----

    def sources(self) -> str:
        return self.conf.get("priority", "website")

    # ---- escape section ----

    def escape_literals(self) -> str:
        return self.conf.get("escape", "literals")

    def escape_folder(self) -> str:
        return self.conf.get("escape", "folders")

    # ---- debug_mode section ----

    def debug(self) -> bool:
        return self.conf.getboolean("debug_mode", "switch")

    # ---- direct section ----

    def get_direct(self) -> bool:
        return self.conf.getboolean("direct", "switch")

    # ---- uncensored section ----

    def get_uncensored(self) -> str:
        return self.conf.get("uncensored", "uncensored_prefix")

    # ---- storyline section ----

    def is_storyline(self) -> bool:
        try:
            return self.conf.getboolean("storyline", "switch")
        except Exception:
            return True

    def storyline_site(self) -> str:
        try:
            return self.conf.get("storyline", "site")
        except Exception:
            return "1:avno1,4:airavwiki"

    def storyline_censored_site(self) -> str:
        try:
            return self.conf.get("storyline", "censored_site")
        except Exception:
            return "2:airav,5:xcity,6:amazon"

    def storyline_uncensored_site(self) -> str:
        try:
            return self.conf.get("storyline", "uncensored_site")
        except Exception:
            return "3:58avgo"

    def storyline_show(self) -> int:
        v = self.conf.getint("storyline", "show_result", fallback=0)
        return v if v in (0, 1, 2) else 2 if v > 2 else 0

    def storyline_mode(self) -> int:
        return 1 if self.conf.getint("storyline", "run_mode", fallback=1) > 0 else 0

    # ---- cc_convert section ----

    def cc_convert_mode(self) -> int:
        v = self.conf.getint("cc_convert", "mode", fallback=1)
        return v if v in (0, 1, 2) else 2 if v > 2 else 0

    def cc_convert_vars(self) -> str:
        return self.conf.get(
            "cc_convert",
            "vars",
            fallback="actor,director,label,outline,series,studio,tag,title",
        )

    # ---- javdb section ----

    def javdb_sites(self) -> str:
        return self.conf.get("javdb", "sites", fallback="38,39")

    # ---- face section ----

    def face_locations_model(self) -> str:
        return self.conf.get("face", "locations_model", fallback="hog")

    def face_uncensored_only(self) -> bool:
        return self.conf.getboolean("face", "uncensored_only", fallback=True)

    def face_aways_imagecut(self) -> bool:
        return self.conf.getboolean("face", "aways_imagecut", fallback=False)

    def face_aspect_ratio(self) -> float:
        return self.conf.getfloat("face", "aspect_ratio", fallback=2.12)

    # ---- jellyfin section ----

    def jellyfin_multi_part_fanart(self) -> bool:
        return self.conf.getboolean("jellyfin", "multi_part_fanart", fallback=False)

    # ---- actor_photo section ----

    def download_actor_photo_for_kodi(self) -> bool:
        return self.conf.getboolean("actor_photo", "download_for_kodi", fallback=False)

    # ---- update section ----

    def update_check(self) -> bool:
        try:
            return self.conf.getboolean("update", "update_check")
        except Exception:
            return False
