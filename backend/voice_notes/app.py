#!/usr/bin/env python3
"""Route hold-to-talk clips: notes → Docs, translate → Spanish speech, remind → Calendar."""

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

from flask import Flask, jsonify, request, Response

DIR = os.path.dirname(os.path.abspath(__file__))
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

app = Flask(__name__)


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


def transcribe(wav_bytes: bytes) -> str:
    import speech_recognition as sr

    recognizer = sr.Recognizer()
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        tmp.write(wav_bytes)
        tmp.flush()
        with sr.AudioFile(tmp.name) as source:
            audio = recognizer.record(source)
    try:
        return recognizer.recognize_google(audio, language="en-US")
    except sr.UnknownValueError:
        return ""


NOTE_PREFIX = re.compile(
    r"^\s*(?:(?:ok|okay|hey)[, ]+)?(?:please[, ]+)?take\s+(?:a\s+)?notes?\b[\s,.:;!\-]*",
    re.IGNORECASE,
)
TRANSLATE_PREFIX = re.compile(
    r"^\s*(?:(?:ok|okay|hey)[, ]+)?(?:please[, ]+)?"
    r"translate(?:\s+this|\s+that)?\b[\s,.:;!\-]*",
    re.IGNORECASE,
)
REMIND_PREFIX = re.compile(
    r"^\s*(?:(?:ok|okay|hey)[, ]+)?(?:please[, ]+)?"
    r"(?:remind\s+me(?:\s+to)?|set\s+(?:a\s+)?reminder(?:\s+to|\s+for)?)\b[\s,.:;!\-]*",
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


def translate_en_to_es(text: str) -> str:
    from deep_translator import GoogleTranslator, MyMemoryTranslator

    try:
        return GoogleTranslator(source="en", target="es").translate(text)
    except Exception:
        return MyMemoryTranslator(source="english", target="spanish").translate(text)


def speak_spanish_pcm(text: str, sample_rate: int, channels: int) -> bytes:
    import miniaudio
    from gtts import gTTS

    mp3 = io.BytesIO()
    gTTS(text=text, lang="es", lang_check=False).write_to_fp(mp3)
    decoded = miniaudio.decode(
        mp3.getvalue(),
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=channels,
        sample_rate=sample_rate,
    )
    return decoded.samples.tobytes()


def json_action(action: str, **payload):
    resp = jsonify({"ok": True, "action": action, **payload})
    resp.headers["X-Action"] = action
    return resp


@app.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "document_id": DOCUMENT_ID,
            "mode": "commands",
            "calendar": calendar_ready(),
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
        wav_bytes = pcm_to_wav(pcm, sample_rate, channels, sample_width)
        transcript = transcribe(wav_bytes).strip()
        action, text = parse_command(transcript)
        if action is None or not text:
            print(f"ignored: {transcript!r}")
            resp = Response(status=204)
            resp.headers["X-Action"] = "none"
            return resp

        if action == "note":
            append_to_doc(text)
            print(f"note: {text}")
            return json_action("note", text=text)

        if action == "remind":
            if not calendar_ready():
                print("remind needs Google Calendar login")
                return json_action("need_login")
            title, when = parse_reminder(text)
            created = create_calendar_event(title, when)
            print(f"remind: {created['when']} {title}")
            return json_action("remind", text=title, when=created["when"])

        spanish = translate_en_to_es(text).strip()
        if not spanish:
            return jsonify({"ok": False, "error": "empty translation"}), 500
        spoken = speak_spanish_pcm(spanish, sample_rate, channels)
        if not spoken:
            return jsonify({"ok": False, "error": "empty speech"}), 500
        print(f"EN: {text}")
        print(f"ES: {spanish}")
        resp = Response(spoken, mimetype="application/octet-stream")
        resp.headers["X-Action"] = "translate"
        resp.headers["X-Sample-Rate"] = str(sample_rate)
        resp.headers["X-Channels"] = str(channels)
        resp.headers["X-Bits"] = "16"
        resp.status_code = 201
        return resp
    except FileNotFoundError as err:
        return jsonify({"ok": False, "error": str(err)}), 500
    except RuntimeError as err:
        return jsonify({"ok": False, "error": str(err)}), 500
    except Exception as err:
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
            "Google Docs is not connected yet. Paste the Apps Script web app URL "
            "into backend/voice_notes/apps_script_url.txt",
            file=sys.stderr,
        )
        return 1

    print(f"Listening on 0.0.0.0:{args.port}")
    print(f"Appending to document {DOCUMENT_ID}")
    if calendar_ready():
        print("Google Calendar connected — next event and reminders enabled")
    else:
        print("Google Calendar not connected. Run ./run.sh --login to show events and add reminders.")
    app.run(host="0.0.0.0", port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
