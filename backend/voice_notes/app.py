#!/usr/bin/env python3
"""Route hold-to-talk clips: notes → Docs, translate → speech, remind → Calendar."""

from __future__ import annotations

import argparse
import array
import audioop
import base64
import io
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, request, Response, send_from_directory

import family
import store

DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(DIR, "static")
CREDENTIALS_PATH = os.path.join(DIR, "credentials.json")
SERVICE_ACCOUNT_PATH = os.path.join(DIR, "service_account.json")
TOKEN_PATH = os.path.join(DIR, "token.json")
WEBHOOK_URL_PATH = os.path.join(DIR, "apps_script_url.txt")
WEBHOOK_SECRET_PATH = os.path.join(DIR, "apps_script_secret.txt")
DOCUMENT_ID = os.environ.get(
    "VOXPIN_DOCUMENT_ID", "1dReqYodsf53bGHCZMvZzoxCcWDqSbux4Fofj5hJ5LY8"
)
DOCUMENT_URL = os.environ.get(
    "VOXPIN_DOCUMENT_URL",
    f"https://docs.google.com/document/d/{DOCUMENT_ID}/edit?tab=t.0",
)
TRANSLATIONS_DOCUMENT_ID = os.environ.get(
    "VOXPIN_TRANSLATIONS_DOCUMENT_ID",
    "1pC-qGeyFBYQv93zwTt15dQTiMnJz6yCgQYGWPQwiCoc",
)
TRANSLATIONS_DOCUMENT_URL = os.environ.get(
    "VOXPIN_TRANSLATIONS_DOCUMENT_URL",
    f"https://docs.google.com/document/d/{TRANSLATIONS_DOCUMENT_ID}/edit",
)
# Primary calendar for reminders + companion month view (from your Calendar share link).
CALENDAR_ID = os.environ.get("VOXPIN_CALENDAR_ID", "riangadey12@gmail.com")
CALENDAR_URL = os.environ.get(
    "VOXPIN_CALENDAR_URL",
    "https://calendar.google.com/calendar/u/0?cid=cmlhbmdhZGV5MTJAZ21haWwuY29t",
)
DOC_SCOPES = ["https://www.googleapis.com/auth/documents"]
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]
SCOPES = CALENDAR_SCOPES + DOC_SCOPES
DEFAULT_PORT = 8765
BEACON_PORT = 8766
TIMEZONE = os.environ.get("VOXPIN_TZ", "America/Los_Angeles")
# Pin buzz+speak lead time. Device treats this as "about 10 minutes away".
ALERT_LEAD_MINUTES = 10

# gTTS language codes for common targets
GTTS_LANG = {
    "zh-CN": "zh-CN",
    "zh-TW": "zh-TW",
}

# macOS `say` voices (offline, much faster than gTTS)
SAY_VOICES = {
    "en": "Samantha",
    "es": "Paulina",
    "fr": "Thomas",
    "de": "Anna",
    "it": "Alice",
    "pt": "Luciana",
    "ja": "Kyoko",
    "ko": "Yuna",
    "zh-CN": "Tingting",
    "zh-TW": "Meijia",
    "hi": "Lekha",
    "ar": "Maged",
    "ru": "Milena",
    "nl": "Xander",
    "pl": "Zosia",
    "sv": "Alva",
    "tr": "Yelda",
    "th": "Kanya",
}

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")


def lan_ipv4s() -> list[str]:
    ips: list[str] = []
    try:
        out = subprocess.check_output(["ifconfig"], text=True)
    except (OSError, subprocess.CalledProcessError):
        return ips
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("inet "):
            continue
        ip = line.split()[1]
        if ip.startswith("127.") or ip.startswith("169.254."):
            continue
        ips.append(ip)
    return ips


def start_helper_beacon(port: int) -> None:
    def loop() -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        while True:
            ips = lan_ipv4s()
            if not ips:
                time.sleep(1.0)
                continue
            for ip in ips:
                msg = f"VOXPIN {ip} {port}".encode("ascii")
                try:
                    sock.sendto(msg, ("255.255.255.255", BEACON_PORT))
                    parts = ip.split(".")
                    if len(parts) == 4:
                        sock.sendto(msg, (f"{parts[0]}.{parts[1]}.{parts[2]}.255", BEACON_PORT))
                except OSError:
                    pass
            time.sleep(1.0)

    threading.Thread(target=loop, name="voxpin-beacon", daemon=True).start()
    print(f"Pin beacon on UDP {BEACON_PORT} from {', '.join(lan_ipv4s()) or 'no LAN IP yet'}")


def hydrate_secrets_from_env() -> None:
    """Write Google/Apps Script files from Fly (or other host) env vars."""

    def write_text(path: str, value: str | None) -> None:
        if not value:
            return
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(value)

    def write_b64_or_text(path: str, b64_key: str, text_key: str) -> None:
        raw_b64 = os.environ.get(b64_key)
        if raw_b64:
            with open(path, "wb") as handle:
                handle.write(base64.b64decode(raw_b64))
            return
        write_text(path, os.environ.get(text_key))

    write_b64_or_text(TOKEN_PATH, "VOXPIN_GOOGLE_TOKEN_B64", "VOXPIN_GOOGLE_TOKEN_JSON")
    write_b64_or_text(
        CREDENTIALS_PATH, "VOXPIN_GOOGLE_CREDENTIALS_B64", "VOXPIN_GOOGLE_CREDENTIALS_JSON"
    )
    write_b64_or_text(
        SERVICE_ACCOUNT_PATH,
        "VOXPIN_GOOGLE_SERVICE_ACCOUNT_B64",
        "VOXPIN_GOOGLE_SERVICE_ACCOUNT_JSON",
    )
    write_text(WEBHOOK_URL_PATH, os.environ.get("VOXPIN_APPS_SCRIPT_URL"))
    write_text(WEBHOOK_SECRET_PATH, os.environ.get("VOXPIN_APPS_SCRIPT_SECRET"))
    data_path = os.path.join(DIR, "voxpin_data.json")
    if not os.path.exists(data_path):
        write_b64_or_text(data_path, "VOXPIN_DATA_B64", "VOXPIN_DATA_JSON")


hydrate_secrets_from_env()


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
        try:
            creds.refresh(Request())
            with open(TOKEN_PATH, "w") as token:
                token.write(creds.to_json())
        except Exception as err:
            print(f"Google token refresh failed ({type(err).__name__}); sign-in needed")
            creds = None
    if creds and creds.valid and creds.has_scopes(SCOPES):
        return creds
    if creds and creds.valid and creds.has_scopes(CALENDAR_SCOPES) and not interactive:
        return creds
    if not interactive:
        raise RuntimeError("Google Calendar login required. Run: ./run.sh --login")
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
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


def docs_api_ready() -> bool:
    try:
        creds = docs_credentials(interactive=False)
        if creds is None:
            return False
        if _is_service_account_file(SERVICE_ACCOUNT_PATH) or _is_service_account_file(
            CREDENTIALS_PATH
        ):
            return True
        return creds.has_scopes(DOC_SCOPES)
    except Exception:
        return False


def docs_ready() -> bool:
    if docs_api_ready():
        return True
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


def reminder_alert_due(
    minutes_until: int | None,
    all_day: bool,
    lead: int = ALERT_LEAD_MINUTES,
) -> bool:
    """True when a timed reminder should buzz/speak on the pin."""
    if all_day or minutes_until is None:
        return False
    return -1 <= minutes_until <= lead


def reminder_spoken(title: str, when: str = "") -> str:
    title = re.sub(r"\s+", " ", (title or "Reminder").strip()) or "Reminder"
    when = re.sub(r"\s+", " ", (when or "").strip())
    if when:
        if re.search(r"\bat\b", when, re.I):
            return f"Reminder. {title} {when}."
        return f"Reminder. {title} at {when}."
    return f"Reminder. {title}."


def _lcd_title(title: str) -> str:
    title = re.sub(r"\s+", " ", (title or "(No title)").replace("\n", " ").strip())
    if len(title) > 48:
        return title[:45] + "..."
    return title


def _minutes_until_iso(raw: str, now: datetime | None = None) -> int | None:
    if not raw or "T" not in raw:
        return None
    now = now or now_local()
    try:
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=_local_tz())
        else:
            stamp = stamp.astimezone(_local_tz())
    except ValueError:
        return None
    return int((stamp - now).total_seconds() // 60)


def _payload_from_google_event(event: dict) -> dict:
    start_info = event.get("start") or {}
    title = (event.get("summary") or "(No title)").replace("\n", " ").strip()
    when = _format_event_when(start_info)
    all_day = "date" in start_info and "dateTime" not in start_info
    start_iso = ""
    minutes = None
    if "dateTime" in start_info:
        try:
            stamp = datetime.fromisoformat(
                start_info["dateTime"].replace("Z", "+00:00")
            ).astimezone(_local_tz())
            start_iso = stamp.isoformat()
            minutes = int((stamp - now_local()).total_seconds() // 60)
        except ValueError:
            minutes = None
    return {
        "when": when,
        "title": _lcd_title(title),
        "full_title": title,
        "id": event.get("id", ""),
        "start": start_iso,
        "minutes_until": minutes,
        "all_day": all_day,
        "alert": reminder_alert_due(minutes, all_day),
        "spoken": reminder_spoken(title, when),
    }


def _payload_from_range_event(event: dict, now: datetime | None = None) -> dict | None:
    if event.get("all_day"):
        return None
    raw = event.get("start") or ""
    minutes = _minutes_until_iso(raw, now)
    if minutes is None:
        return None
    title = (event.get("title") or "Reminder").replace("\n", " ").strip()
    when = event.get("when_label") or ""
    return {
        "when": when,
        "title": _lcd_title(title),
        "full_title": title,
        "id": event.get("id") or "",
        "start": raw,
        "minutes_until": minutes,
        "all_day": False,
        "alert": reminder_alert_due(minutes, False),
        "spoken": reminder_spoken(title, when),
    }


def fetch_next_event() -> dict | None:
    service = calendar_service()
    now = datetime.now(timezone.utc)
    result = (
        service.events()
        .list(
            calendarId=CALENDAR_ID,
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
    return _payload_from_google_event(items[0])


def fetch_next_timed_event(within_hours: int = 24) -> dict | None:
    """Soonest timed calendar item, used for pin buzz+speak stay-awake."""
    if not calendar_ready():
        return None
    now = now_local()
    events = fetch_calendar_range(
        now - timedelta(minutes=1),
        now + timedelta(hours=within_hours),
        limit=12,
    )
    for event in events:
        payload = _payload_from_range_event(event, now)
        if payload is not None:
            return payload
    return None


def fetch_due_reminder() -> dict | None:
    event = fetch_next_timed_event(within_hours=1)
    if event and event.get("alert"):
        return event
    return None


def fetch_calendar_range(start: datetime, end: datetime, limit: int = 12) -> list[dict]:
    service = calendar_service()
    result = (
        service.events()
        .list(
            calendarId=CALENDAR_ID,
            timeMin=start.astimezone(timezone.utc).isoformat(),
            timeMax=end.astimezone(timezone.utc).isoformat(),
            maxResults=limit,
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


def fetch_calendar_events(days: int = 60) -> list[dict]:
    service = calendar_service()
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)
    start = now - timedelta(days=7)
    result = (
        service.events()
        .list(
            calendarId=CALENDAR_ID,
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


def create_calendar_event(
    title: str, start: datetime, duration_minutes: int | None = None
) -> dict:
    service = calendar_service()
    minutes = duration_minutes if duration_minutes and duration_minutes > 0 else 15
    end = start + timedelta(minutes=minutes)
    body = {
        "summary": title,
        "start": {"dateTime": start.isoformat(), "timeZone": TIMEZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": TIMEZONE},
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 0}]},
    }
    created = service.events().insert(calendarId=CALENDAR_ID, body=body).execute()
    if start.date() == now_local().date():
        when_label = start.strftime("%-I:%M %p")
    elif start.date() == now_local().date() + timedelta(days=1):
        when_label = start.strftime("Tomorrow %-I:%M %p")
    else:
        when_label = start.strftime("%a %-I:%M %p")
    return {
        "when": when_label,
        "title": title,
        "id": created.get("id", ""),
        "minutes": minutes,
    }


def append_via_webhook(
    text: str,
    url: str,
    secret: str,
    document_id: str | None = None,
    kind: str = "note",
) -> None:
    import json
    import urllib.request

    now = datetime.now()
    stamp = now.strftime("%Y-%m-%d %-I:%M %p")
    day = now.strftime("%b %-d, %Y")
    if not document_id:
        document_id = (
            TRANSLATIONS_DOCUMENT_ID if kind == "translate" else DOCUMENT_ID
        )
    payload = json.dumps(
        {
            "secret": secret,
            "text": f"{stamp}\n{text}\n\n",
            "day": day,
            "kind": kind,
            "document_id": document_id,
        }
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


def _append_via_docs_api(text: str, document_id: str) -> None:
    service = docs_service()
    document = service.documents().get(
        documentId=document_id, includeTabsContent=True
    ).execute()
    stamp = datetime.now().strftime("%Y-%m-%d %-I:%M %p")
    payload = f"{stamp}\n{text}\n\n"
    tab_id = None
    end_index = None
    tabs = document.get("tabs") or []
    if tabs:
        tab = tabs[0]
        tab_id = (tab.get("tabProperties") or {}).get("tabId")
        content = (
            ((tab.get("documentTab") or {}).get("body") or {}).get("content") or []
        )
        if content:
            end_index = content[-1].get("endIndex")
    if end_index is None:
        end_index = document["body"]["content"][-1]["endIndex"]
    location = {"index": end_index - 1}
    if tab_id:
        location["tabId"] = tab_id
    service.documents().batchUpdate(
        documentId=document_id,
        body={
            "requests": [
                {
                    "insertText": {
                        "location": location,
                        "text": payload,
                    }
                }
            ]
        },
    ).execute()


def append_to_doc(
    text: str, document_id: str | None = None, kind: str = "note"
) -> None:
    if not document_id:
        document_id = (
            TRANSLATIONS_DOCUMENT_ID if kind == "translate" else DOCUMENT_ID
        )
    # The deployed Apps Script still writes every kind into the notes Doc.
    # Use the Docs API when this Mac has document scope so translations land
    # in the translations Doc.
    if docs_api_ready():
        _append_via_docs_api(text, document_id)
        return
    hook = webhook_config()
    if hook:
        append_via_webhook(
            text, hook[0], hook[1], document_id=document_id, kind=kind
        )
        return
    _append_via_docs_api(text, document_id)


def pcm_stats(pcm: bytes, sample_width: int = 2) -> dict:
    if sample_width != 2 or len(pcm) < 2:
        return {"bytes": len(pcm), "rms": 0, "peak": 0, "frames": 0}
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not samples:
        return {"bytes": len(pcm), "rms": 0, "peak": 0, "frames": 0}
    peak = max(abs(sample) for sample in samples)
    rms = int((sum(sample * sample for sample in samples) / len(samples)) ** 0.5)
    return {"bytes": len(pcm), "rms": rms, "peak": peak, "frames": len(samples)}


def extract_channel(pcm: bytes, channels: int, index: int, sample_width: int = 2) -> bytes:
    if channels <= 1:
        return pcm
    frame = channels * sample_width
    offset = index * sample_width
    out = bytearray()
    for i in range(0, len(pcm) - frame + 1, frame):
        out.extend(pcm[i + offset : i + offset + sample_width])
    return bytes(out)


def loudest_mono(pcm: bytes, channels: int, sample_width: int = 2) -> tuple[bytes, int]:
    if channels <= 1:
        return pcm, 0
    best = pcm
    best_rms = -1
    best_ch = 0
    for channel in range(channels):
        mono = extract_channel(pcm, channels, channel, sample_width)
        rms = pcm_stats(mono, sample_width)["rms"]
        if rms > best_rms:
            best_rms = rms
            best = mono
            best_ch = channel
    return best, best_ch


def amplify_pcm(pcm: bytes, sample_width: int = 2, target_peak: int = 12000) -> bytes:
    stats = pcm_stats(pcm, sample_width)
    if stats["peak"] < 80:
        return pcm
    if stats["peak"] >= target_peak:
        return pcm
    factor = min(16.0, target_peak / max(stats["peak"], 1))
    return audioop.mul(pcm, sample_width, factor)


def trim_silence_pcm(pcm: bytes, sample_rate: int, sample_width: int = 2) -> bytes:
    """Drop leading/trailing hush so STT isn't waiting on seconds of quiet."""
    if sample_width != 2 or len(pcm) < sample_rate:
        return pcm
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not samples:
        return pcm
    frame = max(1, sample_rate // 100)
    thresh = 280
    loud = []
    for i in range(0, len(samples), frame):
        peak = 0
        for sample in samples[i : i + frame]:
            mag = -sample if sample < 0 else sample
            if mag > peak:
                peak = mag
        loud.append(peak >= thresh)
    if not any(loud):
        return pcm
    first = next(i for i, is_loud in enumerate(loud) if is_loud)
    last = len(loud) - 1 - next(i for i, is_loud in enumerate(reversed(loud)) if is_loud)
    pad = 8
    start = max(0, (first - pad) * frame)
    end = min(len(samples), (last + 1 + pad) * frame)
    trimmed = samples[start:end]
    if len(trimmed) < sample_rate // 5:
        return pcm
    return trimmed.tobytes()


def pcm_to_wav(pcm: bytes, sample_rate: int, channels: int, sample_width: int) -> bytes:
    if channels > 1:
        pcm, _ = loudest_mono(pcm, channels, sample_width)
        channels = 1
    pcm = amplify_pcm(pcm, sample_width)
    pcm = trim_silence_pcm(pcm, sample_rate, sample_width)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


# Words Google often mishears → what we actually said. Find new ones with:
#   tail -f helper.log | grep heard
CORRECTIONS = {
    r"\b[bvf]ox\s*(?:been|bin|pin|pen)\b": "VoxPin",  # heard "box been 2.0"
}


def fix_words(text: str) -> str:
    for wrong, right in CORRECTIONS.items():
        text = re.sub(wrong, right, text, flags=re.IGNORECASE)
    return text


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
        with urllib.request.urlopen(request, timeout=12) as response:
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
            return fix_words(transcript)
    return ""


NOTE_PREFIX = re.compile(
    r"^\s*(?:(?:ok|okay|hey)[, ]+)?(?:please[, ]+)?"
    r"(?:take\s+(?:a\s+)?notes?|note\s+(?:that|this)?|write\s+(?:this\s+)?down|save\s+(?:a\s+)?note)\b"
    r"[\s,.:;!\-]*",
    re.IGNORECASE,
)
TRANSLATE_PREFIX = re.compile(
    r"^\s*(?:(?:ok|okay|hey)[, ]+)?(?:please[, ]+)?"
    r"(?:translate(?:\s+this|\s+that)?(?:\s+to\s+\w+)?|"
    r"say\s+(?:this\s+)?in(?:\s+\w+)?|"
    r"translation)\b"
    r"[\s,.:;!\-]*",
    re.IGNORECASE,
)
REMIND_PREFIX = re.compile(
    r"^\s*(?:(?:ok|okay|hey)[, ]+)?(?:please[, ]+)?"
    r"(?:remind\s+me(?:\s+to)?|set\s+(?:a\s+)?reminder(?:\s+to|\s+for)?|"
    r"add\s+(?:a\s+)?(?:reminder|event)|reminder(?:\s+to|\s+for)?)\b"
    r"[\s,.:;!\-]*",
    re.IGNORECASE,
)
LOCATION_PREFIX = re.compile(
    r"^\s*(?:(?:ok|okay|hey)[, ]+)?(?:please[, ]+)?"
    r"(?:where\s+am\s+i|share\s+(?:my\s+)?location|send\s+(?:my\s+)?location|"
    r"ping\s+(?:my\s+)?location|find\s+me)\b"
    r"[\s,.:;!\-]*",
    re.IGNORECASE,
)
SOS_PREFIX = re.compile(
    r"^\s*(?:(?:ok|okay|hey)[, ]+)?"
    r"(?:sos|help\s+me|i\s+need\s+help|emergency|call\s+(?:mom|dad|mommy|daddy|mama|papa))\b"
    r"[\s,.:;!\-]*",
    re.IGNORECASE,
)
WEATHER_PREFIX = re.compile(
    r"^\s*(?:(?:ok|okay|hey)[, ]+)?(?:please[, ]+)?"
    r"(?:what(?:'s| is|s)\s+the\s+weather|how(?:'s| is|s)\s+the\s+weather|"
    r"(?:the\s+)?weather|is\s+it\s+(?:going\s+to\s+)?rain(?:ing)?|"
    r"do\s+i\s+need\s+a\s+(?:jacket|coat|umbrella)|"
    r"need\s+a\s+(?:jacket|coat|umbrella))\b"
    r"[\s,.:;!\-]*",
    re.IGNORECASE,
)
TIMER_PREFIX = re.compile(
    r"^\s*(?:(?:ok|okay|hey)[, ]+)?(?:please[, ]+)?"
    r"(?:set\s+(?:a\s+)?timer|timer|countdown|start\s+a\s+timer)\b"
    r"[\s,.:;!\-]*",
    re.IGNORECASE,
)
MORE_MINUTES_PREFIX = re.compile(
    r"^\s*(?:(?:ok|okay|hey)[, ]+)?(?:please[, ]+)?"
    r"(?:(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"fifteen|twenty|thirty)\s+more\s+minutes?|"
    r"(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"fifteen|twenty|thirty)\s+minutes?\s+(?:till|until|to|before))\b",
    re.IGNORECASE,
)
ASK_PREFIX = re.compile(
    r"^\s*(?:(?:ok|okay|hey)[, ]+)?(?:please[, ]+)?"
    r"(?:tell\s+me|read(?:\s+me)?|list|what(?:'s| is|s| are)|who(?:'s| is|s)|"
    r"when(?:'s| is|s)|why|how|do\s+i|did\s+i|can\s+you|could\s+you|"
    r"is\s+there|are\s+there|what\s+time|what\s+do\s+i\s+have)\b",
    re.IGNORECASE,
)
REMINDERS_QUERY = re.compile(
    r"\b(?:reminders?|calendar|schedule|agenda|events?|what(?:'s| is|s)\s+next|"
    r"coming\s+up|what\s+do\s+i\s+have)\b",
    re.IGNORECASE,
)
NOTES_QUERY = re.compile(
    r"\b(?:my\s+notes?|saved\s+notes?|what\s+did\s+i\s+(?:note|write|save))\b",
    re.IGNORECASE,
)
TIME_QUERY = re.compile(
    r"\b(?:what(?:'s| is|s)\s+the\s+time|what\s+time\s+is\s+it|tell\s+me\s+the\s+time)\b",
    re.IGNORECASE,
)
# "5 pm", "5:00 p.m.", "at 5pm" — am/pm required so bare numbers aren't times
CLOCK_TIME = re.compile(
    r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?",
    re.IGNORECASE,
)
# "at 5" / "at 17:30" without am/pm
AT_TIME = re.compile(
    r"\bat\s+(\d{1,2})(?::(\d{2}))?\b",
    re.IGNORECASE,
)
AT_NOON = re.compile(r"\bat\s+noon\b", re.IGNORECASE)
AT_MIDNIGHT = re.compile(r"\bat\s+midnight\b", re.IGNORECASE)
TOMORROW = re.compile(r"\btomorrow\b", re.IGNORECASE)
TODAY = re.compile(r"\btoday\b", re.IGNORECASE)
TONIGHT = re.compile(r"\btonight\b", re.IGNORECASE)
WEEKDAY_INDEX = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}
WEEKDAY_PHRASE = re.compile(
    r"\b(?:on\s+)?(?:(this|next)\s+)?("
    r"monday|mon|tuesday|tues|tue|wednesday|wed|"
    r"thursday|thurs|thur|thu|friday|fri|saturday|sat|sunday|sun"
    r")\b",
    re.IGNORECASE,
)
WORD_HOUR = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
WORD_CLOCK = re.compile(
    r"\b(?:at\s+)?(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
    r"\s*([ap])\.?\s*m\.?",
    re.IGNORECASE,
)


def _soonest_clock(
    now: datetime, hours: list[int], minute: int, day: str = "soonest"
) -> datetime:
    """day: 'today' | 'tomorrow' | 'soonest' (next matching time within a few days)."""
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if day == "tomorrow":
        start += timedelta(days=1)
        offsets = [0]
    elif day == "today":
        offsets = [0]
    else:
        offsets = [0, 1, 2]

    for day_off in offsets:
        day_stamp = start + timedelta(days=day_off)
        candidates = []
        for hour in hours:
            stamp = day_stamp.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if stamp > now:
                candidates.append(stamp)
        if candidates:
            return min(candidates)

    # Explicit "today" but time already passed → same clock tomorrow
    if day == "today":
        return _soonest_clock(now, hours, minute, day="tomorrow")
    return now + timedelta(hours=1)


def _weekday_start(now: datetime, weekday: int, qualifier: str | None) -> datetime:
    """Return midnight of the spoken weekday. 'next Tuesday' skips today."""
    days_ahead = (weekday - now.weekday()) % 7
    if (qualifier or "").lower() == "next" and days_ahead == 0:
        days_ahead = 7
    return now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)


def _hours_from_clock(hour: int, ampm: str) -> list[int]:
    ampm = (ampm or "").lower().replace(".", "")
    if ampm.startswith("p"):
        return [hour % 12 + 12]
    if ampm.startswith("a"):
        return [0 if hour == 12 else hour]
    if hour > 12:
        return [hour]
    return [hour % 12, hour % 12 + 12]


def parse_reminder(text: str) -> tuple[str, datetime, int | None]:
    now = now_local()
    leftover = text
    weekday_match = WEEKDAY_PHRASE.search(leftover)
    weekday_start = None
    if weekday_match:
        weekday_start = _weekday_start(
            now,
            WEEKDAY_INDEX[weekday_match.group(2).lower()],
            weekday_match.group(1),
        )
        leftover = WEEKDAY_PHRASE.sub(" ", leftover, count=1)

    tomorrow = bool(TOMORROW.search(leftover))
    today = bool(TODAY.search(leftover)) and not tomorrow
    leftover = TOMORROW.sub(" ", leftover)
    leftover = TODAY.sub(" ", leftover)
    if weekday_start is not None:
        day = "today" if weekday_start.date() == now.date() else "soonest"
    else:
        day = "tomorrow" if tomorrow else ("today" if today else "soonest")

    when = now + timedelta(hours=1)
    timed = False
    duration_minutes, leftover, duration_role = family.extract_spoken_duration(leftover)

    if AT_NOON.search(leftover):
        when = _soonest_clock(now, [12], 0, day)
        leftover = AT_NOON.sub(" ", leftover)
        timed = True
    elif AT_MIDNIGHT.search(leftover):
        when = _soonest_clock(now, [0], 0, day)
        leftover = AT_MIDNIGHT.sub(" ", leftover)
        timed = True

    match = CLOCK_TIME.search(leftover)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        hours = _hours_from_clock(hour, match.group(3) or "")
        when = _soonest_clock(now, hours, minute, day)
        leftover = CLOCK_TIME.sub(" ", leftover, count=1)
        timed = True
    else:
        match = WORD_CLOCK.search(leftover)
        if match:
            hour = WORD_HOUR[match.group(1).lower()]
            hours = _hours_from_clock(hour, match.group(2) or "")
            when = _soonest_clock(now, hours, 0, day)
            leftover = WORD_CLOCK.sub(" ", leftover, count=1)
            timed = True
        else:
            match = AT_TIME.search(leftover)
            if match:
                hour = int(match.group(1))
                minute = int(match.group(2) or 0)
                hours = _hours_from_clock(hour, "")
                when = _soonest_clock(now, hours, minute, day)
                leftover = AT_TIME.sub(" ", leftover, count=1)
                timed = True

    if duration_minutes is not None and not timed and duration_role != "length":
        when = now + timedelta(minutes=duration_minutes)
        timed = True

    if not timed and TONIGHT.search(leftover):
        when = now.replace(hour=20, minute=0, second=0, microsecond=0)
        if when <= now:
            when += timedelta(days=1)
        leftover = TONIGHT.sub(" ", leftover)
        timed = True

    if not timed and tomorrow:
        when = _soonest_clock(now, [9], 0, "tomorrow")
    elif not timed and today:
        when = _soonest_clock(now, [9], 0, "today")

    leftover = TONIGHT.sub(" ", leftover)
    leftover = re.sub(r"\bon\b", " ", leftover, flags=re.I)
    title = re.sub(r"\s+", " ", leftover).strip(" ,.-")
    title = re.sub(r"^(?:(?:to|for)\s+|\.\s*)+", "", title, flags=re.I).strip(" ,.-")
    if not title:
        title = "Reminder"

    if weekday_start is not None:
        when = weekday_start.replace(
            hour=when.hour, minute=when.minute, second=0, microsecond=0
        )
        if when <= now:
            when += timedelta(days=7)
        if not timed:
            when = when.replace(hour=9, minute=0)
    return title, when, duration_minutes


def duration_spoken(minutes: int | None) -> str:
    if not minutes or minutes <= 0:
        return ""
    hours, mins = divmod(int(minutes), 60)
    parts = []
    if hours == 1:
        parts.append("1 hour")
    elif hours > 1:
        parts.append(f"{hours} hours")
    if mins == 1:
        parts.append("1 minute")
    elif mins > 1:
        parts.append(f"{mins} minutes")
    return " and ".join(parts)


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
    match = LOCATION_PREFIX.match(text)
    if match:
        return "location", text[match.end() :].strip(" ,.-")
    match = SOS_PREFIX.match(text)
    if match:
        return "sos", text[match.end() :].strip(" ,.-")
    match = WEATHER_PREFIX.match(text)
    if match:
        return "weather", text[match.end() :].strip(" ,.-")
    match = TIMER_PREFIX.match(text)
    if match:
        return "timer", text[match.end() :].strip(" ,.-")
    if MORE_MINUTES_PREFIX.match(text):
        return "timer", text
    if ASK_PREFIX.match(text) or REMINDERS_QUERY.search(text) or TIME_QUERY.search(text):
        return "ask", text
    if text:
        # Bare recordings (no command phrase) still go to the Google Doc as notes.
        return "note", text
    return None, text


def _clip_speech(text: str, limit: int = 420) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,.;:") + "."


def reminder_window(text: str) -> tuple[datetime, datetime, str]:
    now = now_local()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    lowered = (text or "").lower()
    if re.search(r"\btomorrow\b", lowered):
        start += timedelta(days=1)
        return start, start + timedelta(days=1), "tomorrow"
    if re.search(r"\b(?:this\s+week|next\s+seven\s+days)\b", lowered):
        return start, start + timedelta(days=7), "this week"
    return start, start + timedelta(days=1), "today"


def upcoming_events(limit: int = 8, text: str = "") -> tuple[list[dict], str]:
    if not calendar_ready():
        return [], "today"
    start, end, label = reminder_window(text)
    now = now_local()
    events = []
    for event in fetch_calendar_range(start, end, limit=limit):
        raw = event.get("start") or ""
        if not raw:
            continue
        try:
            if "T" in raw:
                stamp = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(_local_tz())
            else:
                stamp = datetime.fromisoformat(raw).replace(tzinfo=_local_tz())
        except ValueError:
            events.append(event)
            continue
        if not event.get("all_day") and stamp < now - timedelta(minutes=1):
            continue
        events.append(event)
        if len(events) >= limit:
            break
    return events, label


def speak_reminders(text: str = "") -> str:
    if not calendar_ready():
        return "Calendar isn't signed in yet."
    events, label = upcoming_events(8, text)
    if not events:
        return f"You have no reminders {label}."
    parts = []
    for event in events:
        when = event.get("when_label") or "soon"
        title = event.get("title") or "Reminder"
        parts.append(f"{title} at {when}" if "at" not in when.lower() else f"{title} {when}")
    if len(parts) == 1:
        return f"Today you have {parts[0]}." if label == "today" else f"{label.capitalize()} you have {parts[0]}."
    spoken = (
        f"{'Today' if label == 'today' else label.capitalize()} you have "
        + ", ".join(parts[:-1])
        + ", and "
        + parts[-1]
        + "."
    )
    return _clip_speech(spoken, 420)


def speak_notes() -> str:
    notes = [item for item in store.list_recordings(20) if item.get("kind") == "note"]
    if not notes:
        return "You don't have any saved notes yet."
    latest = [item.get("text") or "" for item in notes[:3] if item.get("text")]
    if not latest:
        return "You don't have any saved notes yet."
    if len(latest) == 1:
        return f"Your latest note is: {latest[0]}."
    return _clip_speech("Your latest notes are: " + ". ".join(latest), 420)


def web_answer(question: str) -> str:
    query = urllib.parse.quote_plus(question)
    headers = {"User-Agent": "VoxPin/1.0"}
    try:
        req = urllib.request.Request(
            f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore") or "{}")
        text = (data.get("AbstractText") or data.get("Answer") or "").strip()
        if not text:
            related = data.get("RelatedTopics") or []
            if related and isinstance(related[0], dict):
                text = (related[0].get("Text") or "").strip()
        if text:
            return _clip_speech(text)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as err:
        print(f"ask ddg failed: {err}", flush=True)

    try:
        req = urllib.request.Request(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{query}",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore") or "{}")
        text = (data.get("extract") or "").strip()
        if text:
            return _clip_speech(text)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as err:
        print(f"ask wiki failed: {err}", flush=True)
    return "I don't know that one yet."


def answer_question(text: str) -> str:
    question = (text or "").strip()
    if TIME_QUERY.search(question):
        return now_local().strftime("It's %-I:%M %p.")
    if NOTES_QUERY.search(question):
        return speak_notes()
    if REMINDERS_QUERY.search(question) or re.search(
        r"\b(?:reminder|calendar|schedule|event)s?\b", question, re.I
    ):
        return speak_reminders(question)
    if len(question) < 2:
        return "I didn't catch the question."
    return web_answer(question)


def spoken_pcm_response(
    text: str,
    action: str,
    status: str,
    sample_rate: int,
    play_channels: int = 2,
):
    spoken = speak_translated_pcm(text, "en", sample_rate, 1)
    if not spoken:
        return json_action(action, status=status, text=text)
    resp = Response(spoken, mimetype="application/octet-stream")
    resp.headers["X-Action"] = action
    resp.headers["X-Status"] = status
    resp.headers["X-Sample-Rate"] = str(sample_rate)
    resp.headers["X-Channels"] = "1"
    resp.headers["X-Bits"] = "16"
    resp.status_code = 201
    return resp


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

    text = (text or "").strip()
    if not text:
        return ""

    import json as json_lib
    import urllib.parse
    import urllib.request

    cache_key = f"{source}|{target}|{text}".lower()
    cache_path = os.path.join(DIR, "translate_cache.json")
    cache: dict = {}
    try:
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as handle:
                cache = json_lib.load(handle) or {}
            hit = cache.get(cache_key)
            if isinstance(hit, str) and hit.strip():
                return hit
    except Exception:
        cache = {}

    def _remember(out: str) -> str:
        try:
            cache[cache_key] = out
            # Keep cache bounded
            if len(cache) > 500:
                for old in list(cache.keys())[: len(cache) - 500]:
                    cache.pop(old, None)
            with open(cache_path, "w", encoding="utf-8") as handle:
                json_lib.dump(cache, handle, ensure_ascii=False)
        except Exception:
            pass
        return out

    # 1) Fast Google gtx endpoint
    gtx_rate_limited = False
    try:
        query = urllib.parse.urlencode(
            {
                "client": "gtx",
                "sl": source,
                "tl": target,
                "dt": "t",
                "q": text,
            }
        )
        url = f"https://translate.googleapis.com/translate_a/single?{query}"
        with urllib.request.urlopen(url, timeout=3) as resp:
            payload = json_lib.loads(resp.read().decode("utf-8"))
        parts = []
        for row in payload[0] or []:
            if row and row[0]:
                parts.append(row[0])
        out = "".join(parts).strip()
        if out:
            return _remember(out)
    except Exception as err:
        err_s = str(err)
        gtx_rate_limited = "429" in err_s
        print(f"translate gtx failed: {err}")

    # 2) MyMemory — use this when Google gtx is down or rate-limited.
    try:
        src = MYMEMORY_LOCALES.get(source_lang, MYMEMORY_LOCALES.get(source, "en-US"))
        dst = MYMEMORY_LOCALES.get(target_lang, MYMEMORY_LOCALES.get(target, "en-US"))
        query = urllib.parse.urlencode({"q": text, "langpair": f"{src}|{dst}"})
        url = f"https://api.mymemory.translated.net/get?{query}"
        with urllib.request.urlopen(url, timeout=4) as resp:
            payload = json_lib.loads(resp.read().decode("utf-8"))
        out = ((payload.get("responseData") or {}).get("translatedText") or "").strip()
        if out and "MYMEMORY WARNING" not in out.upper():
            return _remember(out)
    except Exception as err:
        print(f"translate mymemory failed: {err}")

    # Last resort: another Google scrape. Skip if gtx already 429'd us.
    if not gtx_rate_limited:
        try:
            from deep_translator import GoogleTranslator

            out = GoogleTranslator(source=source, target=target).translate(text)
            out = (out or "").strip()
            if out:
                return _remember(out)
        except Exception as err:
            print(f"translate deep_translator failed: {err}")

    raise RuntimeError("translation failed: empty result")


def translate_from_english(text: str, target_lang: str) -> str:
    return translate_text(text, "en", target_lang)


def append_to_doc_later(
    text: str, document_id: str | None = None, kind: str = "note"
) -> None:
    def _run() -> None:
        try:
            append_to_doc(text, document_id=document_id, kind=kind)
        except Exception as err:
            print(f"note saved locally only (Docs error): {err}", flush=True)

    threading.Thread(target=_run, daemon=True).start()


def _boost_pcm16(mono: bytes, gain: float = 1.2) -> bytes:
    samples = array.array("h")
    samples.frombytes(mono[: len(mono) - (len(mono) % 2)])
    for i, sample in enumerate(samples):
        value = int(sample * gain)
        if value > 32767:
            value = 32767
        elif value < -32767:
            value = -32767
        samples[i] = value
    return samples.tobytes()


def _upmix_mono_pcm(mono: bytes, channels: int) -> bytes:
    if channels <= 1:
        return mono
    samples = array.array("h")
    samples.frombytes(mono[: len(mono) - (len(mono) % 2)])
    out = array.array("h")
    for sample in samples:
        for _ in range(channels):
            out.append(sample)
    return out.tobytes()


def _tts_macos_wav(text: str, lang: str, sample_rate: int) -> bytes | None:
    """Offline macOS TTS via `say` + `afconvert` (~1s). Returns mono 16-bit WAV bytes."""
    if sys.platform != "darwin":
        return None
    voice = SAY_VOICES.get(lang) or SAY_VOICES.get(lang.split("-")[0])
    if not voice:
        return None

    import subprocess

    aiff_path = None
    wav_path = None
    try:
        aiff_path = tempfile.NamedTemporaryFile(suffix=".aiff", delete=False).name
        wav_path = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        say = subprocess.run(
            ["say", "-v", voice, "-r", "155", "-o", aiff_path, text],
            capture_output=True,
            timeout=12,
        )
        if say.returncode != 0:
            print(f"say failed: {say.stderr.decode('utf-8', 'ignore')[:200]}")
            return None
        conv = subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", f"LEI16@{sample_rate}", aiff_path, wav_path],
            capture_output=True,
            timeout=8,
        )
        if conv.returncode != 0:
            print(f"afconvert failed: {conv.stderr.decode('utf-8', 'ignore')[:200]}")
            return None
        with open(wav_path, "rb") as handle:
            return handle.read()
    except Exception as err:
        print(f"macos tts failed: {err}")
        return None
    finally:
        for path in (aiff_path, wav_path):
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass


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
    """Synthesize speech as PCM matching the pin speaker (stereo)."""
    text = (text or "").strip()
    if not text:
        return b""
    play_channels = 1 if channels <= 1 else 2

    # Prefer offline macOS voices — avoids slow/flaky gTTS network round-trips.
    wav_bytes = _tts_macos_wav(text, lang, sample_rate)
    if wav_bytes:
        with wave.open(io.BytesIO(wav_bytes), "rb") as handle:
            mono = handle.readframes(handle.getnframes())
        return _upmix_mono_pcm(_boost_pcm16(mono), play_channels)

    import miniaudio

    decoded = miniaudio.decode(
        tts_mp3_bytes(text, lang),
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
        sample_rate=sample_rate,
    )
    return _upmix_mono_pcm(_boost_pcm16(decoded.samples.tobytes()), play_channels)


def json_action(action: str, *, status: str | None = None, **payload):
    resp = jsonify({"ok": True, "action": action, **payload})
    resp.headers["X-Action"] = action
    if status:
        resp.headers["X-Status"] = status
    return resp


@app.get("/")
@app.get("/index.html")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/companion")
@app.get("/companion.html")
def companion():
    return send_from_directory(STATIC_DIR, "companion.html")


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
            "document_url": DOCUMENT_URL,
            "translations_document_id": TRANSLATIONS_DOCUMENT_ID,
            "translations_document_url": TRANSLATIONS_DOCUMENT_URL,
            "calendar_id": CALENDAR_ID,
            "calendar_url": CALENDAR_URL,
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

    if not os.path.exists(CREDENTIALS_PATH):
        return (
            "<h1>Missing OAuth client</h1>"
            "<p>Calendar needs a Google Cloud <strong>Desktop</strong> OAuth client JSON. "
            "Paste it on the companion <a href='/companion.html#google'>Account</a> tab → Save credentials, "
            "then Sign in again.</p>"
            "<p>(Apps Script alone covers Docs notes, not Calendar.)</p>",
            400,
            {"Content-Type": "text/html; charset=utf-8"},
        )
    if _is_service_account_file(CREDENTIALS_PATH):
        return (
            "<h1>Wrong credential type</h1>"
            "<p><code>credentials.json</code> is a service account. Calendar sign-in needs an "
            "OAuth client JSON with an <code>installed</code> or <code>web</code> key "
            "(Google Cloud → Credentials → Create OAuth client → Desktop app).</p>"
            "<p><a href='/companion.html#google'>Back to Account tab</a></p>",
            400,
            {"Content-Type": "text/html; charset=utf-8"},
        )
    try:
        user_oauth_credentials(interactive=True)
    except Exception as err:
        return (
            f"<h1>Google login failed</h1><pre>{err}</pre>"
            "<p><a href='/companion.html'>Back to VoxPin companion</a></p>",
            500,
            {"Content-Type": "text/html; charset=utf-8"},
        )
    return redirect("/companion.html?google=connected")


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
                "calendar_id": CALENDAR_ID,
                "calendar_url": CALENDAR_URL,
            }
        )
    try:
        events = fetch_calendar_events()
    except Exception as err:
        print(f"calendar list failed: {err}")
        return jsonify({"ok": False, "error": str(err)}), 500
    return jsonify(
        {
            "ok": True,
            "connected": True,
            "events": events,
            "timezone": TIMEZONE,
            "calendar_id": CALENDAR_ID,
            "calendar_url": CALENDAR_URL,
        }
    )


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


@app.get("/reminder-due")
def reminder_due():
    """Upcoming timed reminder for the pin. due=true when it is about 10 minutes away."""
    if not calendar_ready():
        return Response(status=204)
    try:
        event = fetch_next_timed_event()
    except Exception as err:
        print(f"reminder-due failed: {err}")
        return jsonify({"ok": False, "error": str(err)}), 500
    if not event:
        return Response(status=204)
    return jsonify({"ok": True, "due": bool(event.get("alert")), **event})


@app.get("/announce-reminder")
def announce_reminder():
    """PCM speech for a reminder that is about 10 minutes away."""
    if not calendar_ready():
        return Response(status=204)
    try:
        event = fetch_due_reminder()
    except Exception as err:
        print(f"announce-reminder failed: {err}")
        return jsonify({"ok": False, "error": str(err)}), 500
    if not event:
        return Response(status=204)
    spoken = event.get("spoken") or reminder_spoken(
        event.get("full_title") or event.get("title") or "Reminder",
        event.get("when") or "",
    )
    print(f"announce-reminder: {event.get('when')} {event.get('full_title') or event.get('title')}")
    resp = spoken_pcm_response(spoken, "remind", "Reminder", 16000)
    if hasattr(resp, "headers"):
        resp.headers["X-Event-Id"] = event.get("id") or ""
        resp.headers["X-Title"] = event.get("title") or ""
    return resp


def _wifi_from_request() -> list[dict]:
    payload = request.get_json(silent=True) if request.is_json else None
    if isinstance(payload, dict):
        wifi = payload.get("wifi") or []
        if isinstance(wifi, list):
            return wifi
    return []


def handle_parent_ping(kind: str, *, wifi: list[dict] | None = None, detail: str = "") -> dict:
    loc = family.geolocate(wifi)
    place = loc.get("place") or "unknown area"
    maps_url = str(loc.get("maps_url") or "")
    if kind == "sos":
        message = detail.strip() or family.SOS_IMESSAGE
        title = "VoxPin help"
        body = f"{message} near {place}"
        status = "Help sent"
    else:
        message = detail.strip() or "Location shared"
        title = "VoxPin location"
        body = f"{message} · {place}"
        status = "Sent loc"
    alert = store.add_alert(
        kind,
        body,
        place=place,
        maps_url=maps_url or None,
        lat=loc.get("lat"),
        lon=loc.get("lon"),
    )
    store.add_recording(kind, body, when=place)
    notify = family.notify_parent(title, body, kind=kind, maps_url=maps_url)
    if kind == "sos":
        if notify.get("imessage"):
            status = "Help sent"
        elif notify.get("cooldown"):
            status = "Sent already"
        elif notify.get("configured"):
            status = "Msg failed"
        else:
            status = "No iMessage"
    print(f"{kind}: {body} {maps_url} imessage={notify}")
    return {
        "alert": alert,
        "place": place,
        "maps_url": maps_url or None,
        "lat": loc.get("lat"),
        "lon": loc.get("lon"),
        "status": status,
        "source": loc.get("source"),
        "imessage": bool(notify.get("imessage")),
    }


@app.post("/ping")
def ping_location():
    result = handle_parent_ping("ping", wifi=_wifi_from_request())
    return json_action("ping", status=result["status"], **{k: v for k, v in result.items() if k != "status"})


@app.post("/sos")
def sos_alert():
    result = handle_parent_ping("sos", wifi=_wifi_from_request())
    return json_action("sos", status=result["status"], **{k: v for k, v in result.items() if k != "status"})


@app.get("/api/alerts")
def api_alerts():
    return jsonify({"ok": True, "alerts": store.list_alerts()})


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
        stats = pcm_stats(pcm, sample_width)
        t_stt = datetime.now(timezone.utc)
        transcript = transcribe(wav_bytes, language=source).strip()
        stt_s = (datetime.now(timezone.utc) - t_stt).total_seconds()
        print(
            f"clip: {len(pcm)}B -> wav {len(wav_bytes)}B ch={channels} "
            f"rms={stats['rms']} peak={stats['peak']} stt={stt_s:.2f}s",
            flush=True,
        )
        action, text = parse_command(transcript)
        print(f"heard: {transcript!r} -> {action}", flush=True)
        if action is None:
            print(f"ignored: {transcript!r}", flush=True)
            resp = Response(status=204)
            resp.headers["X-Action"] = "none"
            return resp
        if not text and action not in {"translate", "location", "sos", "weather", "ask"}:
            print(f"ignored empty: {transcript!r}", flush=True)
            resp = Response(status=204)
            resp.headers["X-Action"] = "none"
            return resp

        if action == "note":
            store.add_recording("note", text)
            append_to_doc_later(f"Note: {text}", kind="note")
            print(f"note: {text}", flush=True)
            return spoken_pcm_response("Notes added.", "note", "Saved", sample_rate)

        if action == "remind":
            if not calendar_ready():
                print("remind needs Google Calendar login")
                return spoken_pcm_response(
                    "Sign in to Google Calendar on the Mac companion.",
                    "need_login",
                    "Sign in",
                    sample_rate,
                )
            title, when, duration_minutes = parse_reminder(text)
            created = create_calendar_event(title, when, duration_minutes)
            store.add_recording("task", title, when=created["when"])
            print(
                f"remind: {created['when']} {title} ({created.get('minutes')} min)",
                flush=True,
            )
            length = duration_spoken(created.get("minutes") if duration_minutes else None)
            spoken = f"Okay, reminder set. {title}, {created['when']}"
            if length:
                spoken += f", {length}"
            spoken += "."
            return spoken_pcm_response(spoken, "remind", "Reminded", sample_rate)

        if action == "ask":
            spoken = answer_question(text)
            print(f"ask: {text!r} -> {spoken!r}", flush=True)
            return spoken_pcm_response(spoken, "ask", "Answer", sample_rate)

        if action == "timer":
            if not calendar_ready():
                print("timer needs Google Calendar login")
                return json_action("need_login", status="Sign in")
            title, when, minutes = family.parse_timer(text or "10 minutes")
            created = create_calendar_event(title, when, minutes)
            store.add_recording("timer", title, when=created["when"])
            print(f"timer: {minutes} min → {created['when']} {title}")
            return json_action(
                "timer",
                status=f"Timer {minutes}m",
                text=title,
                when=created["when"],
                minutes=minutes,
            )

        if action in {"location", "sos"}:
            result = handle_parent_ping(action if action == "sos" else "ping", detail=text)
            return json_action(result["alert"]["kind"], status=result["status"], **{
                k: v for k, v in result.items() if k != "status"
            })

        if action == "weather":
            loc = family.geolocate()
            summary = family.weather_summary(loc["lat"], loc["lon"])
            store.add_recording("weather", summary["spoken"], when=loc.get("place"))
            spoken = speak_translated_pcm(summary["spoken"], "en", sample_rate, 1)
            if not spoken:
                return json_action("weather", status=summary["status"], text=summary["spoken"])
            resp = Response(spoken, mimetype="application/octet-stream")
            resp.headers["X-Action"] = "weather"
            resp.headers["X-Status"] = summary["status"]
            resp.headers["X-Sample-Rate"] = str(sample_rate)
            resp.headers["X-Channels"] = "1"
            resp.headers["X-Bits"] = "16"
            resp.status_code = 201
            return resp

        target = settings.get("target_language") or "es"
        target_name = settings.get("target_language_name") or "Spanish"
        if not text:
            # User only said "translate this" — ask them to include the phrase.
            prompt = {
                "es": "Di translate this y luego la frase.",
                "en": "Say translate this, then the phrase.",
            }.get(target.split("-")[0], "Say translate this, then the phrase.")
            spoken = speak_translated_pcm(prompt, target, sample_rate, 1)
            resp = Response(spoken, mimetype="application/octet-stream")
            resp.headers["X-Action"] = "translate"
            resp.headers["X-Sample-Rate"] = str(sample_rate)
            resp.headers["X-Channels"] = "1"
            resp.headers["X-Bits"] = "16"
            resp.headers["X-Language"] = target
            resp.status_code = 201
            return resp

        t0 = datetime.now(timezone.utc)
        try:
            translated = translate_text(text, source, target).strip()
        except Exception as err:
            print(f"translate failed: {err}", flush=True)
            return spoken_pcm_response(
                "Translation is busy. Try again in a moment.",
                "translate",
                "Try again",
                sample_rate,
            )
        t1 = datetime.now(timezone.utc)
        if not translated:
            return spoken_pcm_response(
                "Translation is busy. Try again in a moment.",
                "translate",
                "Try again",
                sample_rate,
            )
        spoken = speak_translated_pcm(translated, target, sample_rate, 1)
        t2 = datetime.now(timezone.utc)
        if not spoken:
            return jsonify({"ok": False, "error": "empty speech"}), 500
        store.add_recording(
            "translate",
            text,
            translation=translated,
            language=target_name,
        )
        append_to_doc_later(
            f"Translate ({target_name}): {text} → {translated}",
            document_id=TRANSLATIONS_DOCUMENT_ID,
            kind="translate",
        )
        print(f"{source.upper()}: {text}")
        print(f"{target.upper()}: {translated}")
        print(
            f"translate timing: text={(t1 - t0).total_seconds():.2f}s "
            f"tts={(t2 - t1).total_seconds():.2f}s audio={len(spoken)}B"
        )
        resp = Response(spoken, mimetype="application/octet-stream")
        resp.headers["X-Action"] = "translate"
        resp.headers["X-Sample-Rate"] = str(sample_rate)
        resp.headers["X-Channels"] = "1"
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
        help="Open a browser so this Mac can add reminders and write translations to Google",
    )
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", DEFAULT_PORT)))
    args = parser.parse_args()

    if args.login:
        user_oauth_credentials(interactive=True)
        print("Google Calendar and Docs connected. You can start the server without --login next time.")
        return 0

    if not docs_ready():
        print(
            "Warning: Google Docs is not connected yet. Notes will fail until you paste "
            "the Apps Script web app URL into backend/voice_notes/apps_script_url.txt",
            file=sys.stderr,
        )

    print(f"Listening on 0.0.0.0:{args.port}")
    print(f"Companion website: http://127.0.0.1:{args.port}/")
    print(f"Notes Doc {DOCUMENT_ID}")
    print(f"Translations Doc {TRANSLATIONS_DOCUMENT_ID}")
    if calendar_ready():
        print("Google Calendar connected — next event and reminders enabled")
    else:
        print("Google Calendar not connected. Run ./run.sh --login to show events and add reminders.")
    start_helper_beacon(args.port)
    app.run(host="0.0.0.0", port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
