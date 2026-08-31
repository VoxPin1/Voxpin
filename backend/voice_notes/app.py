#!/usr/bin/env python3
"""Route hold-to-talk clips: 'take notes …' → Google Docs, 'translate this …' → Spanish speech."""

from __future__ import annotations

import argparse
import audioop
import io
import os
import re
import sys
import tempfile
import wave
from datetime import datetime

from flask import Flask, jsonify, request, Response

DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_PATH = os.path.join(DIR, "credentials.json")
SERVICE_ACCOUNT_PATH = os.path.join(DIR, "service_account.json")
TOKEN_PATH = os.path.join(DIR, "token.json")
WEBHOOK_URL_PATH = os.path.join(DIR, "apps_script_url.txt")
WEBHOOK_SECRET_PATH = os.path.join(DIR, "apps_script_secret.txt")
DOCUMENT_ID = "1dReqYodsf53bGHCZMvZzoxCcWDqSbux4Fofj5hJ5LY8"
SCOPES = ["https://www.googleapis.com/auth/documents"]
DEFAULT_PORT = 8765

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
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google.oauth2.service_account import Credentials as ServiceAccountCredentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    sa_path = None
    if os.path.exists(SERVICE_ACCOUNT_PATH):
        sa_path = SERVICE_ACCOUNT_PATH
    elif os.path.exists(CREDENTIALS_PATH) and _is_service_account_file(CREDENTIALS_PATH):
        sa_path = CREDENTIALS_PATH
    if sa_path:
        return ServiceAccountCredentials.from_service_account_file(sa_path, scopes=SCOPES)

    if not os.path.exists(CREDENTIALS_PATH):
        raise FileNotFoundError(
            "Missing Google credentials. Either add a test user and run ./run.sh --login, "
            "or save a service account JSON as backend/voice_notes/service_account.json"
        )

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())
        return creds
    if not interactive:
        raise RuntimeError("Google login required. Run: ./run.sh --login")
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


def parse_command(transcript: str) -> tuple[str | None, str]:
    text = transcript.strip()
    match = NOTE_PREFIX.match(text)
    if match:
        return "note", text[match.end() :].strip(" ,.-")
    match = TRANSLATE_PREFIX.match(text)
    if match:
        return "translate", text[match.end() :].strip(" ,.-")
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
    return jsonify({"ok": True, "document_id": DOCUMENT_ID, "mode": "commands"})


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
    parser.add_argument("--login", action="store_true", help="Open browser to connect Google Docs")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    if args.login:
        docs_credentials(interactive=True)
        print("Google Docs connected. You can start the server without --login next time.")
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
    app.run(host="0.0.0.0", port=args.port, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
