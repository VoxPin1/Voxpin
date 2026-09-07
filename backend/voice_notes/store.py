"""Local persistence for VoxPin companion website."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(DIR, "voxpin_data.json")
_LOCK = threading.Lock()

DEFAULT_SETTINGS = {
    "base_language": "en",
    "base_language_name": "English",
    "target_language": "es",
    "target_language_name": "Spanish",
}

SUPPORTED_LANGUAGES = [
    {"code": "en", "name": "English", "native": "English"},
    {"code": "te", "name": "Telugu", "native": "తెలుగు"},
    {"code": "es", "name": "Spanish", "native": "Español"},
    {"code": "fr", "name": "French", "native": "Français"},
    {"code": "de", "name": "German", "native": "Deutsch"},
    {"code": "it", "name": "Italian", "native": "Italiano"},
    {"code": "pt", "name": "Portuguese", "native": "Português"},
    {"code": "ja", "name": "Japanese", "native": "日本語"},
    {"code": "ko", "name": "Korean", "native": "한국어"},
    {"code": "zh-CN", "name": "Chinese (Simplified)", "native": "简体中文"},
    {"code": "zh-TW", "name": "Chinese (Traditional)", "native": "繁體中文"},
    {"code": "hi", "name": "Hindi", "native": "हिन्दी"},
    {"code": "ar", "name": "Arabic", "native": "العربية"},
    {"code": "ru", "name": "Russian", "native": "Русский"},
    {"code": "nl", "name": "Dutch", "native": "Nederlands"},
    {"code": "pl", "name": "Polish", "native": "Polski"},
    {"code": "sv", "name": "Swedish", "native": "Svenska"},
    {"code": "tr", "name": "Turkish", "native": "Türkçe"},
    {"code": "vi", "name": "Vietnamese", "native": "Tiếng Việt"},
    {"code": "th", "name": "Thai", "native": "ไทย"},
]

# SpeechRecognition / Google STT locale tags
STT_LOCALES = {
    "en": "en-US",
    "te": "te-IN",
    "es": "es-ES",
    "fr": "fr-FR",
    "de": "de-DE",
    "it": "it-IT",
    "pt": "pt-BR",
    "ja": "ja-JP",
    "ko": "ko-KR",
    "zh-CN": "zh-CN",
    "zh-TW": "zh-TW",
    "hi": "hi-IN",
    "ar": "ar-SA",
    "ru": "ru-RU",
    "nl": "nl-NL",
    "pl": "pl-PL",
    "sv": "sv-SE",
    "tr": "tr-TR",
    "vi": "vi-VN",
    "th": "th-TH",
}


def language_by_code(code: str) -> dict[str, str] | None:
    return next((lang for lang in SUPPORTED_LANGUAGES if lang["code"] == code), None)


def stt_locale(code: str) -> str:
    return STT_LOCALES.get(code, code)


def _normalize_settings(settings: dict[str, Any]) -> dict[str, Any]:
    merged = dict(DEFAULT_SETTINGS)
    merged.update(settings or {})
    if "target_language" not in settings:
        # Older data treated base_language as translation target.
        old = settings.get("base_language") or DEFAULT_SETTINGS["target_language"]
        old_name = settings.get("base_language_name") or DEFAULT_SETTINGS["target_language_name"]
        merged["target_language"] = old
        merged["target_language_name"] = old_name
        merged["base_language"] = DEFAULT_SETTINGS["base_language"]
        merged["base_language_name"] = DEFAULT_SETTINGS["base_language_name"]
    return merged


def _empty() -> dict[str, Any]:
    return {"settings": dict(DEFAULT_SETTINGS), "recordings": []}


def _load() -> dict[str, Any]:
    if not os.path.exists(DATA_PATH):
        return _empty()
    try:
        with open(DATA_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
        if "settings" not in data:
            data["settings"] = dict(DEFAULT_SETTINGS)
        else:
            data["settings"] = _normalize_settings(data["settings"])
        if "recordings" not in data:
            data["recordings"] = []
        return data
    except Exception:
        return _empty()


def _save(data: dict[str, Any]) -> None:
    tmp = DATA_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    os.replace(tmp, DATA_PATH)


def get_settings() -> dict[str, Any]:
    with _LOCK:
        return dict(_load()["settings"])


def set_base_language(code: str) -> dict[str, Any]:
    match = language_by_code(code)
    if not match:
        raise ValueError(f"Unsupported language: {code}")
    with _LOCK:
        data = _load()
        data["settings"]["base_language"] = match["code"]
        data["settings"]["base_language_name"] = match["name"]
        _save(data)
        return dict(data["settings"])


def set_target_language(code: str) -> dict[str, Any]:
    match = language_by_code(code)
    if not match:
        raise ValueError(f"Unsupported language: {code}")
    with _LOCK:
        data = _load()
        data["settings"]["target_language"] = match["code"]
        data["settings"]["target_language_name"] = match["name"]
        _save(data)
        return dict(data["settings"])


def list_recordings(limit: int = 200) -> list[dict[str, Any]]:
    with _LOCK:
        items = list(_load()["recordings"])
    items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return items[:limit]


def add_recording(
    kind: str,
    text: str,
    *,
    translation: str | None = None,
    language: str | None = None,
    when: str | None = None,
) -> dict[str, Any]:
    item = {
        "id": str(uuid.uuid4()),
        "kind": kind,
        "text": text,
        "translation": translation,
        "language": language,
        "when": when,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with _LOCK:
        data = _load()
        data["recordings"].insert(0, item)
        data["recordings"] = data["recordings"][:500]
        _save(data)
    return item


def delete_recording(recording_id: str) -> bool:
    with _LOCK:
        data = _load()
        before = len(data["recordings"])
        data["recordings"] = [r for r in data["recordings"] if r.get("id") != recording_id]
        if len(data["recordings"]) == before:
            return False
        _save(data)
        return True
