"""On-request family helpers: location ping, SOS, timers, weather."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any

USER_AGENT = "VoxPin/1.0 (family pin)"
HTTP_TIMEOUT = 8

WORD_NUM = {
    "a": 1,
    "an": 1,
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
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fortyfive": 45,
    "forty-five": 45,
    "sixty": 60,
}


def _http_json(url: str, *, data: dict | None = None, headers: dict | None = None) -> dict:
    body = None
    req_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=req_headers)
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def notify_parent(title: str, body: str) -> None:
    """Laptop notification so a parent sees SOS/location without staring at the site."""
    title = (title or "VoxPin")[:48]
    body = (body or "")[:180]
    if sys.platform != "darwin":
        print(f"parent notify: {title}: {body}")
        return
    def q(text: str) -> str:
        return text.replace("\\", "\\\\").replace('"', '\\"')

    script = (
        f'display notification "{q(body)}" with title "{q(title)}" sound name "Glass"'
    )
    try:
        subprocess.run(["osascript", "-e", script], check=False, timeout=5)
    except Exception as err:
        print(f"parent notify failed: {err}")


def geolocate(wifi: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """WiFi AP geolocation when the pin sends a scan; otherwise the house public IP."""
    aps = []
    for item in wifi or []:
        mac = (item.get("mac") or item.get("macAddress") or "").strip()
        if not mac:
            continue
        entry = {"macAddress": mac}
        rssi = item.get("rssi") if "rssi" in item else item.get("signalStrength")
        if rssi is not None:
            try:
                entry["signalStrength"] = int(rssi)
            except (TypeError, ValueError):
                pass
        aps.append(entry)

    if aps:
        try:
            payload = _http_json(
                "https://api.beacondb.net/v1/geolocate",
                data={"wifiAccessPoints": aps[:12]},
            )
            loc = payload.get("location") or {}
            lat, lon = loc.get("lat"), loc.get("lng")
            if lat is not None and lon is not None:
                return _place(float(lat), float(lon), payload.get("accuracy"), "wifi")
        except Exception as err:
            print(f"wifi geolocate failed: {err}")

    try:
        payload = _http_json("https://ipapi.co/json/")
        lat, lon = payload.get("latitude"), payload.get("longitude")
        if lat is not None and lon is not None:
            city = ", ".join(
                part for part in (payload.get("city"), payload.get("region_code")) if part
            )
            result = _place(float(lat), float(lon), payload.get("accuracy"), "ip")
            if city:
                result["place"] = city
            return result
    except Exception as err:
        print(f"ip geolocate failed: {err}")

    return _place(34.0522, -118.2437, None, "default")


def _place(lat: float, lon: float, accuracy: Any, source: str) -> dict[str, Any]:
    place = reverse_geocode(lat, lon)
    return {
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "accuracy": accuracy,
        "source": source,
        "place": place,
        "maps_url": f"https://maps.google.com/?q={lat:.5f},{lon:.5f}",
    }


def reverse_geocode(lat: float, lon: float) -> str:
    try:
        query = urllib.parse.urlencode(
            {"lat": f"{lat:.5f}", "lon": f"{lon:.5f}", "format": "json"}
        )
        payload = _http_json(
            f"https://nominatim.openstreetmap.org/reverse?{query}",
            headers={"User-Agent": USER_AGENT},
        )
        addr = payload.get("address") or {}
        parts = [
            addr.get("neighbourhood") or addr.get("suburb") or addr.get("hamlet"),
            addr.get("city") or addr.get("town") or addr.get("village"),
        ]
        label = ", ".join(part for part in parts if part)
        return label or (payload.get("display_name") or "").split(",")[0]
    except Exception as err:
        print(f"reverse geocode failed: {err}")
        return ""


def weather_summary(lat: float, lon: float) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {
            "latitude": f"{lat:.4f}",
            "longitude": f"{lon:.4f}",
            "current": "temperature_2m,weather_code,precipitation",
            "hourly": "precipitation_probability",
            "forecast_hours": 6,
            "temperature_unit": "fahrenheit",
            "timezone": os.environ.get("VOXPIN_TZ", "America/Los_Angeles"),
        }
    )
    payload = _http_json(f"https://api.open-meteo.com/v1/forecast?{query}")
    current = payload.get("current") or {}
    hourly = payload.get("hourly") or {}
    temp = current.get("temperature_2m")
    code = int(current.get("weather_code") or 0)
    probs = hourly.get("precipitation_probability") or []
    rain_later = any(int(p or 0) >= 40 for p in probs[:6])
    raining_now = float(current.get("precipitation") or 0) > 0 or code in {
        51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99,
    }
    temp_s = f"{int(temp)} degrees" if temp is not None else "about typical weather"
    if raining_now:
        spoken = f"It's {temp_s} and raining. Grab a jacket."
        status = "Raining"
    elif rain_later:
        spoken = f"It's {temp_s}. Rain later — grab a jacket."
        status = "Rain later"
    else:
        spoken = f"It's {temp_s} and no rain for a while."
        status = "No rain"
    return {
        "temp_f": temp,
        "rain_now": raining_now,
        "rain_later": rain_later,
        "spoken": spoken,
        "status": status,
    }


def parse_minutes(token: str) -> int | None:
    token = (token or "").strip().lower().replace(" ", "")
    if token.isdigit():
        return int(token)
    return WORD_NUM.get(token)


def parse_timer(text: str) -> tuple[str, datetime, int]:
    import re

    now = datetime.now().astimezone()
    try:
        from zoneinfo import ZoneInfo

        now = datetime.now(ZoneInfo(os.environ.get("VOXPIN_TZ", "America/Los_Angeles")))
    except Exception:
        pass

    leftover = text.strip()
    minutes = None

    more = re.search(
        r"\b((?:\d+)|a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve|thirteen|fourteen|fifteen|twenty|thirty|forty-five|fortyfive|forty|sixty)"
        r"\s+more\s+minutes?\b",
        leftover,
        re.I,
    )
    if more:
        minutes = parse_minutes(more.group(1))
        leftover = leftover[: more.start()] + leftover[more.end() :]

    till = re.search(
        r"\b((?:\d+)|a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve|fifteen|twenty|thirty)"
        r"\s+minutes?\s+(?:till|until|to|before)\b",
        leftover,
        re.I,
    )
    if till and minutes is None:
        minutes = parse_minutes(till.group(1))
        leftover = leftover[: till.start()] + leftover[till.end() :]

    dur = re.search(
        r"\b((?:\d+)|a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"fifteen|twenty|thirty)\s*(minutes?|mins?|hours?|hrs?)\b",
        leftover,
        re.I,
    )
    hours = 0
    if dur and minutes is None:
        amount = parse_minutes(dur.group(1)) or 1
        unit = dur.group(2).lower()
        if unit.startswith("hour") or unit.startswith("hr"):
            hours = amount
            minutes = 0
        else:
            minutes = amount
        leftover = leftover[: dur.start()] + leftover[dur.end() :]

    leftover = re.sub(
        r"\b(?:set\s+(?:a\s+)?timer|timer|countdown|for|more)\b",
        " ",
        leftover,
        flags=re.I,
    )
    leftover = re.sub(r"\s+", " ", leftover).strip(" ,.-")
    leftover = re.sub(r"^(?:at|to)\s+", "", leftover, flags=re.I).strip(" ,.-")
    title = leftover or "Timer"
    if minutes is None:
        minutes = 10
    when = now + timedelta(minutes=minutes, hours=hours)
    return title, when, minutes + hours * 60
