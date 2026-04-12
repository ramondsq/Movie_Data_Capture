"""Translation utilities."""

import json
import logging
import re
import time
import uuid

from mdc.http import get_html, post_html
from mdc.utils import is_japanese

logger = logging.getLogger(__name__)


def translate(
    src: str,
    target_language: str = "",
    engine: str = "",
    key: str = "",
    delay: int = 0,
) -> str:
    """Translate text using the configured translation engine."""
    if not target_language or not engine:
        from mdc.config import getInstance
        conf = getInstance()
        target_language = target_language or conf.get_target_language()
        engine = engine or conf.get_translate_engine()
        delay = delay or conf.get_translate_delay()

    # Skip translating Chinese text to Chinese
    if not is_japanese(src) and "zh_" in target_language:
        return src

    trans_result = ""

    if engine == "google-free":
        from mdc.config import getInstance
        gsite = getInstance().get_translate_service_site()
        if not re.match(r"^translate\.google\.(com|com\.\w{2}|\w{2})$", gsite):
            gsite = "translate.google.cn"
        url = (
            f"https://{gsite}/translate_a/single"
            f"?client=gtx&dt=t&dj=1&ie=UTF-8&sl=auto&tl={target_language}&q={src}"
        )
        result = get_html(url=url, return_type="object")
        if not result.ok:
            logger.warning("Google-free translate API call failed.")
            return ""
        translate_list = [i["trans"] for i in result.json()["sentences"]]
        trans_result = "".join(translate_list)

    elif engine == "azure":
        url = f"https://api.cognitive.microsofttranslator.com/translate?api-version=3.0&to={target_language}"
        headers = {
            "Ocp-Apim-Subscription-Key": key,
            "Ocp-Apim-Subscription-Region": "global",
            "Content-type": "application/json",
            "X-ClientTraceId": str(uuid.uuid4()),
        }
        body = json.dumps([{"text": src}])
        result = post_html(url=url, query=body, headers=headers)
        translate_list = [i["text"] for i in result.json()[0]["translations"]]
        trans_result = "".join(translate_list)

    elif engine == "deeplx":
        import requests as req
        from mdc.config import getInstance
        url = getInstance().get_translate_service_site()
        res = req.post(
            f"{url}/translate",
            json={"text": src, "source_lang": "auto", "target_lang": target_language},
        )
        if res.text.strip():
            trans_result = res.json().get("data", "")

    else:
        raise ValueError(f"Non-existent translation engine: {engine}")

    if delay:
        time.sleep(delay)
    return trans_result
