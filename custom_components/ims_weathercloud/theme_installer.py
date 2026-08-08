from __future__ import annotations

import glob
import logging
import os
import re
import shutil

from homeassistant.components import persistent_notification
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import (
    DOMAIN,
    ICONS_DIRNAME,
    ICONS_URL,
    PROFILE_URL,
    THEME_FILE,
    THEME_NAME,
    WEATHER_ICON_MAP,
)

_LOGGER = logging.getLogger(__name__)
_STATIC_KEY = "_icons_static_registered"
_ISSUE_THEMES_NOT_LOADED = "themes_not_loaded"
_NOTIFY_ID = "ims_weathercloud_custom_icons"

NEW_THEME_SENTINEL = "__new__"
_COMMENT_MARKER = "# Animated weather icons"

_NOTIFY = {
    "he": {
        "title": "אייקוני מזג אוויר - IMS + Weathercloud",
        "created": (
            "אייקוני מזג האוויר המותאמים מוכנים בערכת הנושא **{theme}**.\n\n"
            "כדי להפעיל, יש לפתוח את הפרופיל שלך ולבחור את ערכת הנושא:\n\n{url}\n\n"
            "בחירת ערכת נושא נעשית על ידי המשתמש וניתן להגדירה רק שם."
        ),
        "injected": (
            "אייקוני מזג האוויר הוזרקו לערכת הנושא **{theme}**.\n\n"
            "יש לרענן את הדפדפן (Ctrl+F5) כדי לראות אותם."
        ),
    },
    "en": {
        "title": "IMS + Weathercloud icons",
        "created": (
            "Custom weather icons are ready in the **{theme}** theme.\n\n"
            "To enable them, open your profile and select the theme:\n\n{url}\n\n"
            "Theme selection is per-user and can only be set there."
        ),
        "injected": (
            "Custom weather icons were added to the **{theme}** theme.\n\n"
            "Refresh your browser (Ctrl+F5) to see them."
        ),
    },
}


def _lang(hass: HomeAssistant) -> str:
    return "he" if str(hass.config.language or "").lower().startswith("he") else "en"


# --- serving the bundled icons ------------------------------------------
async def async_register_icon_path(hass: HomeAssistant) -> None:
    store = hass.data.setdefault(DOMAIN, {})
    if store.get(_STATIC_KEY):
        return
    icons_dir = os.path.join(os.path.dirname(__file__), ICONS_DIRNAME)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(ICONS_URL, icons_dir, True)]
    )
    store[_STATIC_KEY] = True
    _LOGGER.debug("Serving weather icons from %s at %s", icons_dir, ICONS_URL)


# --- discovery -----------------------------------------------------------
def _themes_dir(config_dir: str) -> str:
    return os.path.join(config_dir, "themes")


def _themes_config_loaded(config_dir: str) -> bool:
    cfg = os.path.join(config_dir, "configuration.yaml")
    if not os.path.isfile(cfg):
        return False
    try:
        lines = open(cfg, encoding="utf-8", errors="ignore").read().splitlines()
    except OSError:
        return False
    in_frontend = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line[0].isspace():
            in_frontend = line.rstrip().startswith("frontend:")
            continue
        if in_frontend and stripped.startswith("themes:"):
            return True
    return False


def _discover_themes(config_dir: str) -> dict[str, str]:
    found: dict[str, str] = {}
    tdir = _themes_dir(config_dir)
    if not os.path.isdir(tdir):
        return found
    for path in sorted(glob.glob(os.path.join(tdir, "*.yaml"))):
        try:
            for line in open(path, encoding="utf-8").read().splitlines():
                m = re.match(r"^([^\s#][^:]*):\s*(#.*)?$", line)
                if m:
                    found.setdefault(m.group(1).strip(), path)
        except OSError:
            continue
    return found


# --- write / inject / remove --------------------------------------------
def _icon_lines(indent: str) -> list[str]:
    return [
        f'{indent}weather-icon-{key}: url("{ICONS_URL}/{fname}")'
        for key, fname in WEATHER_ICON_MAP.items()
    ]


def _expected_icon_values() -> set[str]:
    """The exact set of weather-icon lines we would write (indent-agnostic)."""
    return {ln.strip() for ln in _icon_lines("")}


def _theme_already_current(lines: list[str], theme_name: str) -> bool:
    """True if the theme block already contains exactly our icon lines."""
    rng = _theme_block(lines, theme_name)
    if rng is None:
        return False
    start, end = rng
    present = {
        ln.strip() for ln in lines[start + 1 : end]
        if ln.strip().startswith("weather-icon-")
    }
    return present == _expected_icon_values()


def _standalone_current(path: str) -> bool:
    if not os.path.isfile(path):
        return False
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        return False
    return _theme_already_current(lines, THEME_NAME)


def _is_ours(line: str) -> bool:
    s = line.strip()
    return bool(re.match(r"^weather-icon-\S+\s*:", s)) or s.startswith(_COMMENT_MARKER)


def _theme_block(lines: list[str], theme_name: str) -> tuple[int, int] | None:
    start = None
    for i, line in enumerate(lines):
        if re.match(rf"^{re.escape(theme_name)}:\s*(#.*)?$", line):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^[^\s#][^:]*:\s*(#.*)?$", lines[j]):
            end = j
            break
    return start, end


def _collapse_blanks(lines: list[str]) -> list[str]:
    out: list[str] = []
    for ln in lines:
        if ln.strip() == "" and out and out[-1].strip() == "":
            continue
        out.append(ln)
    return out


def _write_new_theme(config_dir: str) -> str:
    tdir = _themes_dir(config_dir)
    os.makedirs(tdir, exist_ok=True)
    path = os.path.join(tdir, THEME_FILE)
    body = [
        f"{THEME_NAME}:",
        f"  {_COMMENT_MARKER} - managed by IMS + Weathercloud.",
        *_icon_lines("  "),
    ]
    if os.path.exists(path):
        shutil.copy2(path, path + ".bak")
    open(path, "w", encoding="utf-8").write("\n".join(body) + "\n")
    return path


def _inject_into_theme(path: str, theme_name: str) -> None:
    lines = open(path, encoding="utf-8").read().splitlines()
    rng = _theme_block(lines, theme_name)
    if rng is None:
        raise ValueError(f"theme '{theme_name}' not found in {path}")
    start, end = rng

    indent = "  "
    for line in lines[start + 1 : end]:
        if line.strip() and not line.lstrip().startswith("#"):
            indent = line[: len(line) - len(line.lstrip())]
            break

    # strip anything we previously added
    inner = [ln for ln in lines[start + 1 : end] if not _is_ours(ln)]
    new_lines = (
        lines[: start + 1]
        + [f"{indent}{_COMMENT_MARKER} (IMS + Weathercloud)"]
        + _icon_lines(indent)
        + inner
        + lines[end:]
    )
    shutil.copy2(path, path + ".bak")
    open(path, "w", encoding="utf-8").write("\n".join(_collapse_blanks(new_lines)) + "\n")


def _remove_from_theme(path: str, theme_name: str) -> None:
    if not os.path.isfile(path):
        return
    lines = open(path, encoding="utf-8").read().splitlines()
    rng = _theme_block(lines, theme_name)
    if rng is None:
        return
    start, end = rng
    block = lines[start + 1 : end]
    if not any(_is_ours(ln) for ln in block):
        return  # nothing
    cleaned = [ln for ln in block if not _is_ours(ln)]
    new_lines = _collapse_blanks(lines[: start + 1] + cleaned + lines[end:])
    shutil.copy2(path, path + ".bak")
    open(path, "w", encoding="utf-8").write("\n".join(new_lines) + "\n")


def _remove_standalone(config_dir: str) -> None:
    try:
        os.remove(os.path.join(_themes_dir(config_dir), THEME_FILE))
    except FileNotFoundError:
        pass


# --- HA orchestration ----------------------------------------------------
async def _reload_themes(hass: HomeAssistant) -> None:
    if hass.services.has_service("frontend", "reload_themes"):
        hass.async_create_task(
            hass.services.async_call("frontend", "reload_themes", {}, blocking=False)
        )


async def async_discover_themes(hass: HomeAssistant) -> dict[str, str]:
    return await hass.async_add_executor_job(_discover_themes, hass.config.config_dir)


async def async_check_themes_config(hass: HomeAssistant) -> bool:
    ok = await hass.async_add_executor_job(
        _themes_config_loaded, hass.config.config_dir
    )
    if ok:
        ir.async_delete_issue(hass, DOMAIN, _ISSUE_THEMES_NOT_LOADED)
    else:
        ir.async_create_issue(
            hass, DOMAIN, _ISSUE_THEMES_NOT_LOADED,
            is_fixable=False, severity=ir.IssueSeverity.WARNING,
            translation_key=_ISSUE_THEMES_NOT_LOADED,
        )
    return ok


async def _async_theme_is_current(hass: HomeAssistant, path: str, theme_name: str) -> bool:
    def _check() -> bool:
        try:
            lines = open(path, encoding="utf-8").read().splitlines()
        except OSError:
            return False
        return _theme_already_current(lines, theme_name)

    return await hass.async_add_executor_job(_check)


async def _async_standalone_is_current(hass: HomeAssistant) -> bool:
    path = os.path.join(_themes_dir(hass.config.config_dir), THEME_FILE)
    return await hass.async_add_executor_job(_standalone_current, path)


async def async_apply_icons(hass: HomeAssistant, target: str, *, notify: bool = True) -> str:
    await async_check_themes_config(hass)
    config_dir = hass.config.config_dir

    if target and target != NEW_THEME_SENTINEL:
        themes = await async_discover_themes(hass)
        path = themes.get(target)
        if path:
            if await _async_theme_is_current(hass, path, target):
                return target  # already up to date -> do nothing
            await hass.async_add_executor_job(_inject_into_theme, path, target)
            await _reload_themes(hass)
            if notify:
                _notify(hass, target, injected=True)
            return target

    if await _async_standalone_is_current(hass):
        return THEME_NAME  # standalone already correct -> do nothing
    await hass.async_add_executor_job(_write_new_theme, config_dir)
    await _reload_themes(hass)
    if notify:
        _notify(hass, THEME_NAME, injected=False)      # new theme -> profile link
    return THEME_NAME


async def async_remove_icons(hass: HomeAssistant, target: str) -> None:
    config_dir = hass.config.config_dir
    if target and target != NEW_THEME_SENTINEL:
        themes = await async_discover_themes(hass)
        path = themes.get(target)
        if path:
            await hass.async_add_executor_job(_remove_from_theme, path, target)
    else:
        await hass.async_add_executor_job(_remove_standalone, config_dir)
    await _reload_themes(hass)
    persistent_notification.async_dismiss(hass, _NOTIFY_ID)
    ir.async_delete_issue(hass, DOMAIN, _ISSUE_THEMES_NOT_LOADED)


# --- notification --------------------------------------------------------
def _notify(hass: HomeAssistant, theme_name: str, injected: bool) -> None:
    strings = _NOTIFY[_lang(hass)]
    body = strings["injected" if injected else "created"].format(
        theme=theme_name, url=PROFILE_URL
    )
    persistent_notification.async_create(
        hass, body, title=strings["title"], notification_id=_NOTIFY_ID
    )
