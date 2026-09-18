"""Traditional Chinese is local; only new English copy needs a translation service."""

import json
import os
from urllib.request import Request, urlopen
from opencc import OpenCC

TRADITIONAL = OpenCC("s2t")
ENDPOINT = "https://api.cognitive.microsofttranslator.com/translate?api-version=3.0&from=zh-Hans&to=en"


def convert_legacy_languages(value):
    """Upgrade Cantonese-era content without changing its Simplified Chinese source."""
    if isinstance(value, dict):
        if "zh" in value and "en" in value:
            value.pop("yue", None)
            value["hant"] = TRADITIONAL.convert(value["zh"])
        else:
            for child in value.values():
                convert_legacy_languages(child)
    elif isinstance(value, list):
        for child in value:
            convert_legacy_languages(child)
    return value


def translate_changes(content, previous):
    known = {}
    pending = []

    def collect(value):
        if isinstance(value, dict):
            if set(value) == {"zh", "en", "hant"}:
                if value["en"]:
                    known[value["zh"].strip()] = value["en"]
            else:
                for child in value.values():
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(previous)

    def visit(value):
        if isinstance(value, dict):
            if set(value) == {"zh", "en", "hant"}:
                source = value["zh"].strip()
                value["hant"] = TRADITIONAL.convert(value["zh"])
                value["en"] = known.get(source, "")
                if source and not value["en"]:
                    pending.append(value)
            else:
                for child in value.values():
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(content)
    if not pending:
        return []
    key = os.environ.get("AZURE_TRANSLATOR_KEY", "")
    if not key:
        return [
            "简体和繁体中文已保存；未配置英文翻译服务，新增或改写的英文内容待翻译。"
        ]
    try:
        batches, batch, characters = [], [], 0
        for item in pending:
            if batch and (characters + len(item["zh"]) > 20000 or len(batch) >= 10):
                batches.append(batch)
                batch, characters = [], 0
            batch.append(item)
            characters += len(item["zh"])
        if batch:
            batches.append(batch)
        for batch in batches:
            request = Request(
                ENDPOINT,
                data=json.dumps([{"Text": item["zh"]} for item in batch]).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Ocp-Apim-Subscription-Key": key,
                    "Ocp-Apim-Subscription-Region": os.environ.get(
                        "AZURE_TRANSLATOR_REGION", ""
                    ),
                },
                method="POST",
            )
            with urlopen(request, timeout=25) as response:
                result = json.load(response)
            if len(result) != len(batch):
                raise ValueError("Incomplete response")
            for item, row in zip(batch, result):
                english = next(
                    (
                        entry["text"]
                        for entry in row["translations"]
                        if entry["to"] == "en"
                    ),
                    None,
                )
                if not english:
                    raise ValueError("Missing English translation")
                item["en"] = english
    except Exception:
        return ["简体和繁体中文已保存；英文翻译未全部完成，请检查翻译服务后再次保存。"]
    return []
