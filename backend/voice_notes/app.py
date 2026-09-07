#!/usr/bin/env python3
"""Route hold-to-talk clips: notes → Docs, translate → speech, remind → Calendar."""

from __future__ import annotations

import argparse
import audioop
import io
import os
import re
import sys
import tempfile
import wave
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, request, Response, send_from_directory

import store

DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(DIR, "static")
CREDENTIALS_PATH = os.path.join(DIR, "credentials.json")
SERVICE_ACCOUNT_PATH = os.path.join(DIR, "service_account.json")
TOKEN_PATH = os.path.join(DIR, "token.json")
WEBHOOK_URL_PATH = os.path.join(DIR, "apps_script_url.txt")
WEBHOOK_SECRET_PATH = os.path.join(DIR, "apps_script_secret.txt")
DOCUMENT_ID = "1dReqYodsf53bGHCZMvZzoxCcWDqSbux4Fofj5hJ5LY8"
DOC_SCOPES = ["https://www.googleapis.com/auth/documents"]
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]
SCOPES = DOC_SCOPES + CALENDAR_SCOPES
DEFAULT_PORT = 8765
TIMEZONE = os.environ.get("VOXPIN_TZ", "America/Los_Angeles")

# gTTS language codes for common targets
GTTS_LANG = {
    "zh-CN": "zh-CN",
    "zh-TW": "zh-TW",
}

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")


def _is_service_account_file(path: str) -> bool:
    try:
        import json

        with open(path) as handle:
            data = json.load(handle)
        return data.get("type") == "service_account"
    except Exception:
        return False


def docs_credentials(interactive: bool = True):
    from google.oauth2.service_account import Credentials as ServiceAccountCredentials

    sa_path = None
    if os.path.exists(SERVICE_ACCOUNT_PATH):
        sa_path = SERVICE_ACCOUNT_PATH
    elif os.path.exists(CREDENTIALS_PATH) and _is_service_account_file(CREDENTIALS_PATH):
        sa_path = CREDENTIALS_PATH
    if sa_path:
        return ServiceAccountCredentials.from_service_account_file(sa_path, scopes=DOC_SCOPES)

    if not os.path.exists(CREDENTIALS_PATH):
        raise FileNotFoundError(
            "Missing Google credentials. Either add a test user and run ./run.sh --login, "
            "or save a service account JSON as backend/voice_notes/service_account.json"
        )

    return user_oauth_credentials(interactive=interactive)


def _local_tz():
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(TIMEZONE)
    except Exception:
        return datetime.now().astimezone().tzinfo or timezone.utc


def now_local() -> datetime:
    return datetime.now(_local_tz())


def user_oauth_credentials(interactive: bool = True):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not os.path.exists(CREDENTIALS_PATH):
        raise FileNotFoundError(
            "Missing Google credentials. Add credentials.json and run ./run.sh --login"
        )

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())
    if creds and creds.valid and creds.has_scopes(CALENDAR_SCOPES):
        return creds
    if not interactive:
        raise RuntimeError("Google Calendar login required. Run: ./run.sh --login")
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
    creds = flow.run_local_server(port=0)
    with open(TOKEN_PATH, "w") as token:
        token.write(creds.to_json())
    return creds


def webhook_config():
    if not os.path.exists(WEBHOOK_URL_PATH):
        return None
    url = open(WEBHOOK_URL_PATH, encoding="utf-8").read().strip()
    if not url:
        return None
    secret = ""
    if os.path.exists(WEBHOOK_SECRET_PATH):
        secret = open(WEBHOOK_SECRET_PATH, encoding="utf-8").read().strip()
    return url, secret


def docs_ready() -> bool:
    if webhook_config():
        return True
    if os.path.exists(SERVICE_ACCOUNT_PATH) or _is_service_account_file(CREDENTIALS_PATH):
        return True
    return os.path.exists(TOKEN_PATH)


def docs_service():
    from googleapiclient.discovery import build

    return build("docs", "v1", credentials=docs_credentials(interactive=False))


def calendar_ready() -> bool:
    if not os.path.exists(TOKEN_PATH) or not os.path.exists(CREDENTIALS_PATH):
        return False
    try:
        creds = user_oauth_credentials(interactive=False)
        return creds.has_scopes(CALENDAR_SCOPES)
    except Exception:
        return False


def calendar_service():
    from googleapiclient.discovery import build

    return build("calendar", "v3", credentials=user_oauth_credentials(interactive=False))


def _format_event_when(start: dict) -> str:
    now = now_local()
    if "dateTime" in start:
        dt = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00")).astimezone(_local_tz())
        if dt.date() == now.date():
            return dt.strftime("%-I:%M %p")
        if dt.date() == (now.date() + timedelta(days=1)):
            return dt.strftime("Tomorrow %-I:%M %p")
        return dt.strftime("%a %-I:%M %p")
    day = datetime.strptime(start["date"], "%Y-%m-%d").date()
    if day == now.date():
        return "Today"
    if day == now.date() + timedelta(days=1):
        return "Tomorrow"
    return datetime.combine(day, datetime.min.time()).strftime("%a %b %-d")


def fetch_next_event() -> dict | None:
    service = calendar_service()
    now = datetime.now(timezone.utc)
    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now.isoformat(),
            maxResults=1,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    items = result.get("items") or []
    if not items:
        return None
    event = items[0]
    title = (event.get("summary") or "(No title)").replace("\n", " ").strip()
    if len(title) > 48:
        title = title[:45] + "..."
    return {"when": _format_event_when(event.get("start") or {}), "title": title}


def fetch_calendar_events(days: int = 60) -> list[dict]:
    service = calendar_service()
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)
    start = now - timedelta(days=7)
    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            maxResults=250,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    events = []
    for event in result.get("items") or []:
        start_info = event.get("start") or {}
        end_info = event.get("end") or {}
        events.append(
            {
                "id": event.get("id", ""),
                "title": (event.get("summary") or "(No title)").strip(),
                "start": start_info.get("dateTime") or start_info.get("date"),
                "end": end_info.get("dateTime") or end_info.get("date"),
                "all_day": "date" in start_info and "dateTime" not in start_info,
                "when_label": _format_event_when(start_info),
            }
        )
    return events


def create_calendar_event(title: str, start: datetime) -> dict:
    service = calendar_service()
    end = start + timedelta(minutes=15)
    body = {
        "summary": title,
        "start": {"dateTime": start.isoformat(), "timeZone": TIMEZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": TIMEZONE},
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 0}]},
    }
    created = service.events().insert(calendarId="primary", body=body).execute()
    return {
        "when": start.strftime("%-I:%M %p"),
        "title": title,
        "id": created.get("id", ""),
    }


def append_via_webhook(text: str, url: str, secret: str) -> None:
    import json
    import urllib.request

    now = datetime.now()
    stamp = now.strftime("%Y-%m-%d %-I:%M %p")
    day = now.strftime("%b %-d, %Y")
    payload = json.dumps(
        {"secret": secret, "text": f"{stamp}\n{text}\n\n", "day": day}
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if not body.get("ok"):
        raise RuntimeError(body.get("error", "Apps Script append failed"))


def append_to_doc(text: str) -> None:
    hook = webhook_config()
    if hook:
        append_via_webhook(text, hook[0], hook[1])
        return

    service = docs_service()
    document = service.documents().get(documentId=DOCUMENT_ID).execute()
    end_index = document["body"]["content"][-1]["endIndex"]
    stamp = datetime.now().strftime("%Y-%m-%d %-I:%M %p")
    payload = f"{stamp}\n{text}\n\n"
    service.documents().batchUpdate(
        documentId=DOCUMENT_ID,
        body={
            "requests": [
                {
                    "insertText": {
                        "location": {"index": end_index - 1},
                        "text": payload,
                    }
                }
            ]
        },
    ).execute()


def pcm_to_wav(pcm: bytes, sample_rate: int, channels: int, sample_width: int) -> bytes:
    if channels == 2:
        pcm = audioop.tomono(pcm, sample_width, 0.5, 0.5)
        channels = 1
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def transcribe(wav_bytes: bytes, language: str = "en") -> str:
    """Speech-to-text via Google's web endpoint using LINEAR16 (no flac binary)."""
    import json
    import urllib.error
    import urllib.parse
    import urllib.request

    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        sample_rate = wf.getframerate()
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        pcm = wf.readframes(wf.getnframes())

    if channels == 2:
        pcm = audioop.tomono(pcm, sample_width, 0.5, 0.5)
        channels = 1
    if sample_width != 2:
        pcm = audioop.lin2lin(pcm, sample_width, 2)
        sample_width = 2
    if sample_rate < 8000:
        pcm, _ = audioop.ratecv(pcm, 2, 1, sample_rate, 8000, None)
        sample_rate = 8000

    if len(pcm) < sample_rate // 10:
        return ""

    locale = store.stt_locale(language)
    # Same public Chromium key SpeechRecognition uses for the free web endpoint.
    key = "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"
    params = urllib.parse.urlencode(
        {
            "client": "chromium",
            "lang": locale,
            "key": key,
            "pFilter": 0,
        }
    )
    url = f"https://www.google.com/speech-api/v2/recognize?{params}"
    request = urllib.request.Request(
        url,
        data=pcm,
        headers={"Content-Type": f"audio/l16; rate={sample_rate}; channels=1"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_text = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")[:200]
        raise RuntimeError(f"speech recognition HTTP {err.code}: {detail}") from err
    except Exception as err:
        raise RuntimeError(f"speech recognition failed: {err}") from err

    for line in response_text.splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        results = payload.get("result") or []
        if not results:
            continue
        alternatives = results[0].get("alternative") or []
        if not alternatives:
            continue
        transcript = (alternatives[0].get("transcript") or "").strip()
        if transcript:
            return transcript
    return ""


NOTE_PREFIX = re.compile(
    r"^\s*(?:(?:ok|okay|hey)[, ]+)?(?:please[, ]+)?"
    r"(?:take\s+(?:a\s+)?notes?|note\s+(?:that|this)?|write\s+(?:this\s+)?down|save\s+(?:a\s+)?note)\b"
    r"[\s,.:;!\-]*",
    re.IGNORECASE,
)
TRANSLATE_PREFIX = re.compile(
    r"^\s*(?:(?:ok|okay|hey)[, ]+)?(?:please[, ]+)?"
    r"(?:translate(?:\s+this|\s+that)?(?:\s+to\s+\w+)?|say\s+(?:this\s+)?in(?:\s+\w+)?)\b"
    r"[\s,.:;!\-]*",
    re.IGNORECASE,
)
REMIND_PREFIX = re.compile(
    r"^\s*(?:(?:ok|okay|hey)[, ]+)?(?:please[, ]+)?"
    r"(?:remind\s+me(?:\s+to)?|set\s+(?:a\s+)?reminder(?:\s+to|\s+for)?|add\s+(?:a\s+)?(?:reminder|event))\b"
    r"[\s,.:;!\-]*",
    re.IGNORECASE,
)
IN_DURATION = re.compile(
    r"\bin\s+(?:an?\s+)?(\d+)?\s*(minutes?|mins?|hours?|hrs?)\b",
    re.IGNORECASE,
)
AT_TIME = re.compile(
    r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?\b",
    re.IGNORECASE,
)
AT_NOON = re.compile(r"\bat\s+noon\b", re.IGNORECASE)
AT_MIDNIGHT = re.compile(r"\bat\s+midnight\b", re.IGNORECASE)
TOMORROW = re.compile(r"\btomorrow\b", re.IGNORECASE)
TONIGHT = re.compile(r"\btonight\b", re.IGNORECASE)


def _soonest_clock(now: datetime, hours: list[int], minute: int, tomorrow: bool) -> datetime:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if tomorrow:
        start += timedelta(days=1)
    for day_off in range(0, 3):
        day = start + timedelta(days=day_off)
        candidates = []
        for hour in hours:
            stamp = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if stamp > now:
                candidates.append(stamp)
        if candidates:
            return min(candidates)
        if tomorrow:
            break
    return now + timedelta(hours=1)


def parse_reminder(text: str) -> tuple[str, datetime]:
    now = now_local()
    tomorrow = bool(TOMORROW.search(text))
    leftover = TOMORROW.sub(" ", text)

    when = now + timedelta(hours=1)
    timed = False

    if AT_NOON.search(leftover):
        when = _soonest_clock(now, [12], 0, tomorrow)
        leftover = AT_NOON.sub(" ", leftover)
        timed = True
    elif AT_MIDNIGHT.search(leftover):
        when = _soonest_clock(now, [0], 0, tomorrow)
        leftover = AT_MIDNIGHT.sub(" ", leftover)
        timed = True

    match = AT_TIME.search(leftover)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        ampm = (match.group(3) or "").lower().replace(".", "")
        if ampm.startswith("p"):
            hours = [hour % 12 + 12]
        elif ampm.startswith("a"):
            hours = [0 if hour == 12 else hour]
        elif hour > 12:
            hours = [hour]
        else:
            hours = [hour % 12, hour % 12 + 12]
        when = _soonest_clock(now, hours, minute, tomorrow)
        leftover = AT_TIME.sub(" ", leftover)
        timed = True

    match = IN_DURATION.search(leftover)
    if match:
        amount = int(match.group(1) or 1)
        unit = match.group(2).lower()
        if unit.startswith("hour") or unit.startswith("hr"):
            when = now + timedelta(hours=amount)
        else:
            when = now + timedelta(minutes=amount)
        leftover = IN_DURATION.sub(" ", leftover)
        timed = True

    if not timed and TONIGHT.search(leftover):
        when = now.replace(hour=20, minute=0, second=0, microsecond=0)
        if when <= now:
            when += timedelta(days=1)
        leftover = TONIGHT.sub(" ", leftover)
        timed = True

    if not timed and tomorrow:
        when = _soonest_clock(now, [9], 0, True)

    leftover = TONIGHT.sub(" ", leftover)
    title = re.sub(r"\s+", " ", leftover).strip(" ,.-")
    title = re.sub(r"^(?:to|for)\s+", "", title, flags=re.I).strip(" ,.-")
    if not title:
        title = "Reminder"
    return title, when


def parse_command(transcript: str) -> tuple[str | None, str]:
    text = transcript.strip()
    match = NOTE_PREFIX.match(text)
    if match:
        return "note", text[match.end() :].strip(" ,.-")
    match = TRANSLATE_PREFIX.match(text)
    if match:
        return "translate", text[match.end() :].strip(" ,.-")
    match = REMIND_PREFIX.match(text)
    if match:
        return "remind", text[match.end() :].strip(" ,.-")
    return None, text


GREETING_EN = "Hello, Are you ready to start your Journey!"

# Reliable offline greetings so language clicks never depend on a live translator
GREETING_BY_LANG = {
    "en": GREETING_EN,
    "te": "హలో, మీరు మీ ప్రయాణాన్ని ప్రారంభించడానికి సిద్ధంగా ఉన్నారా!",
    "es": "¡Hola, estás listo para comenzar tu viaje!",
    "fr": "Bonjour, êtes-vous prêt à commencer votre voyage !",
    "de": "Hallo, bist du bereit, deine Reise zu beginnen!",
    "it": "Ciao, sei pronto a iniziare il tuo viaggio!",
    "pt": "Olá, você está pronto para começar a sua jornada!",
    "ja": "こんにちは、旅を始める準備はできていますか！",
    "ko": "안녕하세요, 여행을 시작할 준비가 되셨나요!",
    "zh-CN": "你好，准备好开始你的旅程了吗！",
    "zh-TW": "你好，準備好開始你的旅程了嗎！",
    "hi": "नमस्ते, क्या आप अपनी यात्रा शुरू करने के लिए तैयार हैं!",
    "ar": "مرحبًا، هل أنت مستعد لبدء رحلتك!",
    "ru": "Привет, ты готов начать своё путешествие!",
    "nl": "Hallo, ben je klaar om aan je reis te beginnen!",
    "pl": "Cześć, czy jesteś gotowy, aby rozpocząć swoją podróż!",
    "sv": "Hej, är du redo att börja din resa!",
    "tr": "Merhaba, yolculuğuna başlamaya hazır mısın!",
    "vi": "Xin chào, bạn đã sẵn sàng bắt đầu hành trình chưa!",
    "th": "สวัสดี คุณพร้อมที่จะเริ่มต้นการเดินทางแล้วหรือยัง!",
}

MYMEMORY_LOCALES = {
    "en": "en-US",
    "te": "te-IN",
    "es": "es-ES",
    "fr": "fr-FR",
    "de": "de-DE",
    "it": "it-IT",
    "pt": "pt-PT",
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


def greeting_for_language(code: str) -> str:
    if code in GREETING_BY_LANG:
        return GREETING_BY_LANG[code]
    try:
        return translate_from_english(GREETING_EN, code).strip() or GREETING_EN
    except Exception:
        return GREETING_EN


def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    source = (source_lang or "en").split("-")[0]
    target = (target_lang or "en").split("-")[0] if target_lang else "en"
    if source == target:
        return text

    from deep_translator import GoogleTranslator, MyMemoryTranslator

    try:
        return GoogleTranslator(source=source, target=target).translate(text)
    except Exception:
        src = MYMEMORY_LOCALES.get(source_lang, MYMEMORY_LOCALES.get(source, "en-US"))
        dst = MYMEMORY_LOCALES.get(target_lang, MYMEMORY_LOCALES.get(target, "en-US"))
        try:
            return MyMemoryTranslator(source=src, target=dst).translate(text)
        except Exception as err:
            raise RuntimeError(f"translation failed: {err}") from err


def translate_from_english(text: str, target_lang: str) -> str:
    return translate_text(text, "en", target_lang)


def tts_mp3_bytes(text: str, lang: str) -> bytes:
    from gtts import gTTS

    tts_lang = GTTS_LANG.get(lang, lang.split("-")[0])
    mp3 = io.BytesIO()
    try:
        gTTS(text=text, lang=tts_lang, lang_check=False).write_to_fp(mp3)
    except Exception:
        # Last resort: speak English so the click never hard-fails
        mp3 = io.BytesIO()
        gTTS(text=text if lang.startswith("en") else GREETING_EN, lang="en", lang_check=False).write_to_fp(mp3)
    return mp3.getvalue()


def speak_translated_pcm(text: str, lang: str, sample_rate: int, channels: int) -> bytes:
    import miniaudio

    decoded = miniaudio.decode(
        tts_mp3_bytes(text, lang),
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=channels,
        sample_rate=sample_rate,
    )
    return decoded.samples.tobytes()


def json_action(action: str, **payload):
    resp = jsonify({"ok": True, "action": action, **payload})
    resp.headers["X-Action"] = action
    return resp


@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/health")
def health():
    settings = store.get_settings()
    return jsonify(
        {
            "ok": True,
            "document_id": DOCUMENT_ID,
            "mode": "commands",
            "calendar": calendar_ready(),
            "base_language": settings.get("base_language"),
            "base_language_name": settings.get("base_language_name"),
        }
    )


@app.get("/api/status")
def api_status():
    settings = store.get_settings()
    return jsonify(
        {
            "ok": True,
            "calendar": calendar_ready(),
            "docs": docs_ready(),
            "base_language": settings.get("base_language"),
            "base_language_name": settings.get("base_language_name"),
            "target_language": settings.get("target_language"),
            "target_language_name": settings.get("target_language_name"),
            "recording_count": len(store.list_recordings()),
            "document_id": DOCUMENT_ID,
            "has_credentials": os.path.exists(CREDENTIALS_PATH)
            or os.path.exists(SERVICE_ACCOUNT_PATH)
            or bool(webhook_config()),
            "has_token": os.path.exists(TOKEN_PATH),
        }
    )


@app.get("/api/google/status")
def api_google_status():
    return jsonify(
        {
            "ok": True,
            "docs": docs_ready(),
            "calendar": calendar_ready(),
            "has_credentials": os.path.exists(CREDENTIALS_PATH),
            "has_service_account": os.path.exists(SERVICE_ACCOUNT_PATH),
            "has_apps_script": bool(webhook_config()),
            "has_token": os.path.exists(TOKEN_PATH),
            "document_id": DOCUMENT_ID,
            "document_url": f"https://docs.google.com/document/d/{DOCUMENT_ID}/edit",
        }
    )


@app.post("/api/google/credentials")
def api_google_credentials():
    """Save a Google Cloud OAuth Desktop client JSON as credentials.json."""
    import json as json_lib

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"ok": False, "error": "Paste the full credentials JSON"}), 400
    if "installed" not in data and "web" not in data:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "JSON must be an OAuth client (keys: installed or web). "
                    "In Google Cloud → APIs & Services → Credentials → Create OAuth client → Desktop app.",
                }
            ),
            400,
        )
    with open(CREDENTIALS_PATH, "w", encoding="utf-8") as handle:
        json_lib.dump(data, handle, indent=2)
    return jsonify({"ok": True, "has_credentials": True})


@app.post("/api/google/apps-script")
def api_google_apps_script():
    """Restore the Apps Script webhook URL (+ optional secret) used for Docs notes."""
    body = request.get_json(silent=True) or {}
    url = (body.get("url") or "").strip()
    secret = (body.get("secret") or "").strip()
    if not url.startswith("https://script.google.com/"):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "URL must be an Apps Script web app link "
                    "(https://script.google.com/macros/s/.../exec)",
                }
            ),
            400,
        )
    with open(WEBHOOK_URL_PATH, "w", encoding="utf-8") as handle:
        handle.write(url + "\n")
    with open(WEBHOOK_SECRET_PATH, "w", encoding="utf-8") as handle:
        handle.write(secret + "\n")
    return jsonify({"ok": True, "docs": docs_ready(), "has_apps_script": True})


@app.post("/api/google/apps-script/test")
def api_google_apps_script_test():
    """Send a probe line to the Doc via Apps Script."""
    hook = webhook_config()
    if not hook:
        return jsonify({"ok": False, "error": "Apps Script URL not saved yet"}), 400
    try:
        append_via_webhook("VoxPin Apps Script test — connection OK", hook[0], hook[1])
    except Exception as err:
        return jsonify({"ok": False, "error": str(err)}), 500
    return jsonify({"ok": True, "message": "Wrote a test line to the Doc"})


@app.get("/api/google/connect")
def api_google_connect():
    """Open a browser Google login, then return to the companion site."""
    from flask import redirect

    if not os.path.exists(CREDENTIALS_PATH) and not _is_service_account_file(CREDENTIALS_PATH):
        return (
            "<h1>Missing credentials.json</h1>"
            "<p>Paste your Google OAuth Desktop client JSON on the companion "
            "<a href='/#google'>Google</a> tab first.</p>",
            400,
            {"Content-Type": "text/html; charset=utf-8"},
        )
    try:
        user_oauth_credentials(interactive=True)
    except Exception as err:
        return (
            f"<h1>Google login failed</h1><pre>{err}</pre>"
            "<p><a href='/'>Back to VoxPin</a></p>",
            500,
            {"Content-Type": "text/html; charset=utf-8"},
        )
    return redirect("/?google=connected")


@app.get("/api/recordings")
def api_recordings():
    return jsonify({"ok": True, "recordings": store.list_recordings()})


@app.delete("/api/recordings/<recording_id>")
def api_delete_recording(recording_id: str):
    if not store.delete_recording(recording_id):
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True})


@app.get("/api/languages")
def api_languages():
    settings = store.get_settings()
    return jsonify(
        {
            "ok": True,
            "languages": store.SUPPORTED_LANGUAGES,
            "base_language": settings.get("base_language"),
            "base_language_name": settings.get("base_language_name"),
            "target_language": settings.get("target_language"),
            "target_language_name": settings.get("target_language_name"),
            # Back-compat for older UI
            "selected": settings.get("base_language"),
            "selected_name": settings.get("base_language_name"),
        }
    )


@app.get("/api/settings")
def api_get_settings():
    return jsonify({"ok": True, **store.get_settings()})


@app.put("/api/settings/language")
def api_set_language():
    body = request.get_json(silent=True) or {}
    code = (body.get("code") or body.get("language") or "").strip()
    role = (body.get("role") or "base").strip().lower()
    if not code:
        return jsonify({"ok": False, "error": "code required"}), 400
    try:
        if role == "target":
            settings = store.set_target_language(code)
        else:
            settings = store.set_base_language(code)
    except ValueError as err:
        return jsonify({"ok": False, "error": str(err)}), 400
    return jsonify({"ok": True, **settings})


@app.get("/api/speak-greeting")
def api_speak_greeting():
    """Translate the journey greeting into a language and return MP3 speech."""
    import base64

    code = (request.args.get("code") or "en").strip()
    if not store.language_by_code(code):
        return jsonify({"ok": False, "error": "unsupported language"}), 400

    spoken = greeting_for_language(code)
    try:
        mp3 = tts_mp3_bytes(spoken, code)
    except Exception as err:
        print(f"speak-greeting tts failed: {err}")
        try:
            mp3 = tts_mp3_bytes(GREETING_EN, "en")
            spoken = spoken or GREETING_EN
        except Exception as err2:
            return jsonify({"ok": False, "error": str(err2)}), 500

    return jsonify(
        {
            "ok": True,
            "code": code,
            "text": spoken,
            "audio_base64": base64.b64encode(mp3).decode("ascii"),
            "mime": "audio/mpeg",
        }
    )


@app.get("/api/calendar")
def api_calendar():
    if not calendar_ready():
        return jsonify(
            {
                "ok": True,
                "connected": False,
                "events": [],
                "message": "Connect Google Calendar with ./run.sh --login",
            }
        )
    try:
        events = fetch_calendar_events()
    except Exception as err:
        print(f"calendar list failed: {err}")
        return jsonify({"ok": False, "error": str(err)}), 500
    return jsonify({"ok": True, "connected": True, "events": events, "timezone": TIMEZONE})


@app.get("/next-event")
def next_event():
    if not calendar_ready():
        return Response(status=204)
    try:
        event = fetch_next_event()
    except Exception as err:
        print(f"next-event failed: {err}")
        return jsonify({"ok": False, "error": str(err)}), 500
    if not event:
        return Response(status=204)
    return jsonify({"ok": True, **event})


@app.post("/note")
def note():
    pcm = request.get_data(cache=False)
    if not pcm:
        return jsonify({"ok": False, "error": "empty audio"}), 400

    sample_rate = int(request.headers.get("X-Sample-Rate", "16000"))
    channels = int(request.headers.get("X-Channels", "2"))
    bits = int(request.headers.get("X-Bits", "16"))
    sample_width = max(1, bits // 8)

    try:
        settings = store.get_settings()
        # Command phrases are English ("take notes", "translate this", …).
        # Always STT in English so Language-tab picks don't break recognition.
        source = "en"
        wav_bytes = pcm_to_wav(pcm, sample_rate, channels, sample_width)
        transcript = transcribe(wav_bytes, language=source).strip()
        action, text = parse_command(transcript)
        if action is None or not text:
            print(f"ignored: {transcript!r}")
            resp = Response(status=204)
            resp.headers["X-Action"] = "none"
            return resp

        if action == "note":
            docs_ok = True
            try:
                append_to_doc(text)
            except FileNotFoundError as err:
                docs_ok = False
                print(f"note saved locally only (Docs not connected): {err}")
            except Exception as err:
                docs_ok = False
                print(f"note saved locally only (Docs error): {err}")
            store.add_recording("note", text)
            print(f"note: {text}")
            # Always treat local save as success so the pin doesn't look broken
            # when Google Docs isn't linked yet.
            if not docs_ok:
                return json_action("note_local", text=text)
            return json_action("note", text=text)

        if action == "remind":
            if not calendar_ready():
                print("remind needs Google Calendar login")
                return json_action("need_login")
            title, when = parse_reminder(text)
            created = create_calendar_event(title, when)
            store.add_recording("task", title, when=created["when"])
            print(f"remind: {created['when']} {title}")
            return json_action("remind", text=title, when=created["when"])

        target = settings.get("target_language") or "es"
        target_name = settings.get("target_language_name") or "Spanish"
        translated = translate_text(text, source, target).strip()
        if not translated:
            return jsonify({"ok": False, "error": "empty translation"}), 500
        spoken = speak_translated_pcm(translated, target, sample_rate, channels)
        if not spoken:
            return jsonify({"ok": False, "error": "empty speech"}), 500
        store.add_recording(
            "translate",
            text,
            translation=translated,
            language=target_name,
        )
        print(f"{source.upper()}: {text}")
        print(f"{target.upper()}: {translated}")
        resp = Response(spoken, mimetype="application/octet-stream")
        resp.headers["X-Action"] = "translate"
        resp.headers["X-Sample-Rate"] = str(sample_rate)
        resp.headers["X-Channels"] = str(channels)
        resp.headers["X-Bits"] = "16"
        resp.headers["X-Language"] = target
        resp.status_code = 201
        return resp
    except FileNotFoundError as err:
        print(f"/note FileNotFoundError: {err}")
        return jsonify({"ok": False, "error": str(err)}), 500
    except RuntimeError as err:
        print(f"/note RuntimeError: {err}")
        return jsonify({"ok": False, "error": str(err)}), 500
    except Exception as err:
        print(f"/note Exception: {type(err).__name__}: {err}")
        return jsonify({"ok": False, "error": str(err)}), 500


def main() -> int:
    parser = argparse.ArgumentParser(description="VoxPin voice-note backend")
    parser.add_argument(
        "--login",
        action="store_true",
        help="Open browser to connect Google Docs and Google Calendar",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    if args.login:
        user_oauth_credentials(interactive=True)
        print("Google Calendar connected. You can start the server without --login next time.")
        return 0

    if not docs_ready():
        print(
            "Warning: Google Docs is not connected yet. Notes will fail until you paste "
            "the Apps Script web app URL into backend/voice_notes/apps_script_url.txt",
            file=sys.stderr,
        )

    print(f"Listening on 0.0.0.0:{args.port}")
    print(f"Companion website: http://127.0.0.1:{args.port}/")
    print(f"Appending to document {DOCUMENT_ID}")
    if calendar_ready():
        print("Google Calendar connected — next event and reminders enabled")
    else:
        print("Google Calendar not connected. Run ./run.sh --login to show events and add reminders.")
    app.run(host="0.0.0.0", port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
