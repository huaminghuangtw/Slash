"""
Rewrites the generated sections of uses.md: `# Obsidian Plugins` from the
community plugins enabled in the vault, `# Browser Extensions` from the ones
installed in Brave. Plugin repo links come from the obsidian-releases registry;
extension links from their homepage, the curated SITES map, or the Chrome Web
Store.
"""

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
USES = REPO / "uses.md"
VAULT = Path(
    os.environ.get(
        "SECOND_BRAIN_VAULT",
        Path.home()
        / "Library/Mobile Documents/iCloud~md~obsidian/Documents/Second-Brain",
    )
)
CONFIG = VAULT / ".obsidian/community-plugins.json"
PLUGINS = VAULT / ".obsidian/plugins"
REGISTRY = (
    "https://raw.githubusercontent.com/obsidianmd/obsidian-releases"
    "/master/community-plugins.json"
)
BROWSER = Path(
    os.environ.get(
        "BRAVE_PROFILE",
        Path.home()
        / "Library/Application Support/BraveSoftware/Brave-Browser/Default",
    )
)
EXTENSIONS = BROWSER / "Extensions"
STORE = "https://chromewebstore.google.com/detail/"
# Extensions whose manifest has no homepage_url.
SITES = {
    "eimadpbcbfnmbkopoojfekhnkhdbieeh": "https://darkreader.org",
    "khncfooichmfjbepaaaebmommgaepoid": "https://unhook.app",
    "laookkfknpbbblfpciffpaejjkokdgca": "https://momentumdash.com",
    "ponfpcnoihfmfllpaingbgckeeldkhle": "https://www.mrfdev.com/enhancer-for-youtube",
}
PLUGINS_HEADING = "# Obsidian Plugins"
PLUGINS_BEFORE = "# macOS Tools"
EXTENSIONS_HEADING = "# Browser Extensions"
EXTENSIONS_BEFORE = "# Miscellaneous"


def enabled() -> list[str]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def names() -> dict[str, str]:
    found = {}
    for plugin in enabled():
        manifest = PLUGINS / plugin / "manifest.json"
        if manifest.is_file():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            found[plugin] = data["name"]
    return found


def repos() -> dict[str, str]:
    with urllib.request.urlopen(REGISTRY, timeout=30) as response:
        registry = json.load(response)
    return {entry["id"]: entry["repo"] for entry in registry}


def plugin_block(names: dict[str, str], repos: dict[str, str]) -> list[str]:
    lines = [PLUGINS_HEADING, ""]
    for plugin, name in sorted(names.items(), key=lambda item: item[1].casefold()):
        repo = repos.get(plugin)
        if repo:
            lines.append(f"* [{name}](https://github.com/{repo})")
        else:
            lines.append(f"* {name}")
            print(f"uses.md: {plugin} is not in the registry, left unlinked",
                  file=sys.stderr)
    return lines


def manifest_of(folder: Path) -> Path | None:
    manifests = [path / "manifest.json" for path in folder.iterdir()
                 if path.is_dir()]
    present = [path for path in manifests if path.is_file()]
    return max(present, key=lambda path: path.stat().st_mtime, default=None)


def resolved(value: str | None, manifest: Path) -> str:
    placeholder = re.fullmatch(r"__MSG_(.+)__", value or "")
    if not placeholder:
        return value or ""
    for code in ("en", "en_US"):
        messages = manifest.parent / "_locales" / code / "messages.json"
        if messages.is_file():
            data = json.loads(messages.read_text(encoding="utf-8"))
            if data.get(placeholder.group(1)):
                return data[placeholder.group(1)]["message"]
    return ""


def label(data: dict, manifest: Path) -> str:
    for field in ("short_name", "name"):
        name = resolved(data.get(field), manifest)
        if name:
            return name.strip()
    return manifest.parent.name


def link(extension: str, data: dict) -> str:
    homepage = (data.get("homepage_url") or "").rstrip("/")
    return SITES.get(extension) or homepage or STORE + extension


def extensions() -> list[tuple[str, str]]:
    found = []
    for folder in sorted(EXTENSIONS.iterdir()):
        manifest = manifest_of(folder) if folder.is_dir() else None
        if not manifest:
            continue
        data = json.loads(manifest.read_text(encoding="utf-8"))
        found.append((label(data, manifest), link(folder.name, data)))
    return found


def extension_block(found: list[tuple[str, str]]) -> list[str]:
    lines = [EXTENSIONS_HEADING, ""]
    for name, url in sorted(found, key=lambda item: item[0].casefold()):
        lines.append(f"* [{name}]({url})")
    return lines


def bounds(lines: list[str], heading: str) -> tuple[int, int] | None:
    for start, line in enumerate(lines):
        if line.strip() == heading:
            end = start + 1
            while end < len(lines) and not lines[end].startswith("# "):
                end += 1
            while end > start + 1 and not lines[end - 1].strip():
                end -= 1
            return start, end
    return None


def splice(text: str, heading: str, before: str, block: list[str]) -> str:
    lines = text.splitlines()
    found = bounds(lines, heading)
    if found:
        start, end = found
    else:
        anchor = next(
            (i for i, line in enumerate(lines) if line.strip() == before), None
        )
        if anchor is None:
            sys.exit(f"uses.md: neither {heading!r} nor {before!r} found")
        end = start = anchor
    while start > 0 and not lines[start - 1].strip():
        start -= 1
    if not found:
        end = start
    return "\n".join(lines[:start] + [""] + block + lines[end:]) + "\n"


def main() -> int:
    text = USES.read_text(encoding="utf-8")
    counts = {}

    plugins = names()
    if plugins:
        text = splice(text, PLUGINS_HEADING, PLUGINS_BEFORE,
                      plugin_block(plugins, repos()))
        counts["plugins"] = len(plugins)

    browsers = extensions() if EXTENSIONS.is_dir() else []
    if browsers:
        text = splice(text, EXTENSIONS_HEADING, EXTENSIONS_BEFORE,
                      extension_block(browsers))
        counts["extensions"] = len(browsers)

    summary = ", ".join(f"{count} {kind}" for kind, count in counts.items())
    if text == USES.read_text(encoding="utf-8"):
        print(f"uses.md: unchanged, {summary}")
        return 0

    USES.write_text(text, encoding="utf-8")
    print(f"uses.md: updated, {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
