"""Point /now at where I actually am.

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
SUFFIXES = (
    "County", "City", "Province", "Prefecture", "District", "Region",
    "Township", "Municipality", "State",
)


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
    """Most specific first; GeoNames knows "Chiayi", not "Chiayi County"."""
    queries: list[str] = []
    for segment in reversed(segments[:-1]):
        for query in (segment, strip_suffix(segment)):
            if query and query not in queries:
                queries.append(query)
    return queries


def strip_suffix(segment: str) -> str:
    words = segment.split()
    while len(words) > 1 and words[-1].rstrip(".") in SUFFIXES:
        words.pop()
    return " ".join(words)


def resolve(segments: list[str]) -> dict | None:
    country = segments[-1].casefold()
    for query in queries_for(segments):
        try:
            results = geocode(query)
        except OSError as error:
            print(f"geocode {query!r} failed: {error}", file=sys.stderr)
            continue
        for result in results:
            if (result.get("country") or "").casefold() == country:
                return result
        if results:
            return results[0]
    return None


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


def main() -> int:
    found = journal_location()
    if not found:
        print(f"no journal location in the last {LOOKBACK_DAYS} days", file=sys.stderr)
        return 0

    raw, day = found
    segments = [part.strip() for part in raw.split(",") if part.strip()]
    label = ", ".join(segments[-2:])

    lines, rest, before = read_now()
    place = resolve(segments)
    if place:
        set_field(lines, "location", json.dumps(
            f"{flag(place['country_code'])} {label}", ensure_ascii=False))
        set_field(lines, "latitude", json.dumps(round(place["latitude"], 4)))
        set_field(lines, "longitude", json.dumps(round(place["longitude"], 4)))
        set_field(lines, "timeZone", json.dumps(place["timezone"]))
    else:
        set_field(lines, "location", json.dumps(label, ensure_ascii=False))

    updated = "---\n" + "\n".join(lines) + "\n---" + rest
    if updated == before:
        print(f"now.md: up to date ({label}, {day})")
        return 0

    NOW.write_text(updated, encoding="utf-8")
    print(f"now.md: {label} from {day}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
