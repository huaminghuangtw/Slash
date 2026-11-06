"""
Reads the newest Daily-Bullet-Journal `location:` line, keeps its last two
segments (region, country — the city is dropped), resolves coordinates and
time zone with the Open-Meteo geocoder, and writes all of it into now.md's
frontmatter. `/now` then shows the flag + region, and drives its clock and
weather from the stored coordinates.
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NOW = REPO / "now.md"
JOURNAL = (
    Path(
        os.environ.get(
            "SECOND_BRAIN_VAULT",
            Path.home()
            / "Library/Mobile Documents/iCloud~md~obsidian/Documents/Second-Brain",
        )
    )
    / "Daily-Bullet-Journal/journals"
)
GEOCODER = "https://geocoding-api.open-meteo.com/v1/search"
LOOKBACK_DAYS = 30

FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---", re.DOTALL)
LOCATION_LINE = re.compile(r"^location:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
PLAIN_UNSAFE = re.compile(r"""^[\s\-?:,\[\]{}#&*!|>'\"%@`]|: | #|\s$""")
SUFFIXES = (
    "County", "City", "Province", "Prefecture", "District", "Region",
    "Township", "Municipality", "State",
)
COUNTRY_ALIASES = {
    "usa": "united states",
    "us": "united states",
    "united states of america": "united states",
    "uk": "united kingdom",
    "u.k.": "united kingdom",
    "great britain": "united kingdom",
    "uae": "united arab emirates",
}


def flag(iso2: str) -> str:
    return "".join(chr(0x1F1E6 + ord(letter) - ord("A")) for letter in iso2.upper())


def journal_location() -> tuple[str, date] | None:
    day = date.today()
    for _ in range(LOOKBACK_DAYS):
        path = JOURNAL / f"{day:%Y}" / f"{day:%m-%B}" / f"{day:%Y_%m_%d}.md"
        if path.is_file():
            block = FRONTMATTER.match(path.read_text(encoding="utf-8"))
            line = LOCATION_LINE.search(block.group(1)) if block else None
            if line:
                return line.group(1).strip("\"'"), day
        day -= timedelta(days=1)
    return None


def geocode(query: str) -> list[dict]:
    params = urllib.parse.urlencode(
        {"name": query, "count": 10, "language": "en", "format": "json"}
    )
    with urllib.request.urlopen(f"{GEOCODER}?{params}", timeout=10) as response:
        return json.load(response).get("results") or []


def queries_for(segments: list[str]) -> list[str]:
    """Most specific first — the city, then the areas that contain it."""
    queries: list[str] = []
    for segment in segments[:-1]:
        for query in (segment, strip_suffix(segment)):
            if query and query not in queries:
                queries.append(query)
    return queries


def strip_suffix(segment: str) -> str:
    words = segment.split()
    while len(words) > 1 and words[-1].rstrip(".") in SUFFIXES:
        words.pop()
    return " ".join(words)


def country_of(segment: str) -> str:
    key = segment.casefold()
    return COUNTRY_ALIASES.get(key, key)


def matches(result: dict, country: str) -> bool:
    return country_of(result.get("country") or "") == country


def in_region(result: dict, region: str) -> bool:
    """Is the place inside the journal's named area (state, county, province)?"""
    haystack = " ".join(
        str(result.get(key) or "") for key in ("name", "admin1", "admin2", "admin3")
    ).casefold()
    return region in haystack or strip_suffix(region) in haystack


def resolve(segments: list[str]) -> dict | None:
    """Prefer a hit inside the named area; accept the country's best match otherwise."""
    country = country_of(segments[-1])
    region = segments[1].casefold() if len(segments) > 2 else None
    fallback: dict | None = None
    for query in queries_for(segments):
        try:
            results = geocode(query)
        except OSError as error:
            print(f"geocode {query!r} failed: {error}", file=sys.stderr)
            continue
        for result in results:
            if not matches(result, country):
                continue
            if not region or in_region(result, region):
                return result
            fallback = fallback or result
    return fallback


def read_now() -> tuple[list[str], str, str]:
    text = NOW.read_text(encoding="utf-8")
    block = FRONTMATTER.match(text)
    if not block:
        sys.exit("now.md: no frontmatter block")
    return block.group(1).splitlines(), text[block.end():], text


def set_field(lines: list[str], key: str, value: str) -> None:
    pattern = re.compile(rf"^{re.escape(key)}:")
    for index, line in enumerate(lines):
        if pattern.match(line):
            lines[index] = f"{key}: {value}"
            return
    lines.append(f"{key}: {value}")


def scalar(value: str) -> str:
    """Plain YAML unless the value needs quoting."""
    if value and not PLAIN_UNSAFE.search(value):
        return value
    return json.dumps(value, ensure_ascii=False)


def main() -> int:
    found = journal_location()
    if not found:
        print(
            f"no journal location in the last {LOOKBACK_DAYS} days", file=sys.stderr)
        return 0

    raw, day = found
    segments = [part.strip() for part in raw.split(",") if part.strip()]
    label = ", ".join(segments[-2:])

    lines, rest, before = read_now()
    place = resolve(segments)
    if place:
        set_field(lines, "location", scalar(f"{flag(place['country_code'])} {label}"))
        set_field(lines, "latitude", json.dumps(round(place['latitude'], 4)))
        set_field(lines, "longitude", json.dumps(round(place['longitude'], 4)))
        set_field(lines, "timeZone", scalar(place["timezone"]))
    else:
        set_field(lines, "location", scalar(label))

    updated = "---\n" + "\n".join(lines) + "\n---" + rest
    if updated == before:
        print(f"now.md: up to date ({label}, {day})")
        return 0

    NOW.write_text(updated, encoding="utf-8")
    print(f"now.md: {label} from {day}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
