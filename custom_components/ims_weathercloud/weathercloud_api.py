"""Thin async wrapper around the ``weathercloud`` (>=1.0) SDK.

All Weathercloud I/O lives here so the coordinator and the config flow only
deal with one small class. The module deliberately has no Home Assistant
imports, which keeps it testable on its own (see ``tests/``).

Why not use the SDK's own ``client.auth.login``:
Weathercloud answers a good login with ``302 -> /`` and a bad one with
``200`` + the sign-in page again. The SDK follows redirects and treats every
2xx as success, so it cannot tell the two apart. We post the same form
ourselves on the shared ``httpx`` client and look at the status code, the way
``weathercloud`` 0.1.x did.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import asdict, dataclass
from typing import Any

import httpx
from weathercloud import AsyncWeathercloudClient
from weathercloud.core.api_error import ApiError
from weathercloud.core.parse_error import ParsingError

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://app.weathercloud.net"
DEFAULT_TIMEOUT = 10.0  # seconds, same as weathercloud 0.1.x

# Weathercloud serves its JSON endpoints to browser-like XHR requests.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)
_ICAO_RE = re.compile(r"^[A-Z]{4}$")

# Indoor readings are only returned to the station owner's session.
INDOOR_FIELDS = ("tempin", "humin", "heatin")

# Status codes that mean "your session is gone" on a JSON endpoint.
_AUTH_STATUSES = {301, 302, 303, 307, 308, 401, 403}

# When indoor values vanish while logged in, re-login at most this often.
_RELOGIN_COOLDOWN = 3600.0


# The station page embeds its position as JavaScript variables.
_LAT_RE = re.compile(r"var\s+latitude\s*=\s*(-?[\d.]+)\s*;")
_LON_RE = re.compile(r"var\s+longitude\s*=\s*(-?[\d.]+)\s*;")
_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class StationInfo:
    """Static facts about a station, fetched once per load."""

    name: str | None = None
    city: str | None = None
    altitude: float | None = None  # metres
    latitude: float | None = None
    longitude: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_station_page(html: str) -> tuple[str | None, float | None, float | None]:
    """Name and coordinates from a public station page (no login needed)."""
    name = None
    if m := _TITLE_RE.search(html):
        name = re.split(r"\s+-\s+Weathercloud", m.group(1), flags=re.IGNORECASE)[0].strip() or None
    lat = _float(m.group(1)) if (m := _LAT_RE.search(html)) else None
    lon = _float(m.group(1)) if (m := _LON_RE.search(html)) else None
    # 0,0 is what an unset position looks like; anything out of range is junk.
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        lat = lon = None
    elif lat == 0 and lon == 0:
        lat = lon = None
    return name, lat, lon


class WeathercloudApiError(Exception):
    """Weathercloud could not be reached or returned something unusable."""


class WeathercloudAuthError(WeathercloudApiError):
    """Username or password were rejected."""


class WeathercloudApi:
    """One Weathercloud station, one long-lived HTTP session."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        device_id: str,
        username: str | None = None,
        password: str | None = None,
        base_url: str = BASE_URL,
    ) -> None:
        self._http = http
        self._device_id = str(device_id).strip()
        self._username = username or None
        self._password = password or None
        self._base_url = base_url.rstrip("/")
        self._logged_in = False
        self._had_indoor = False
        self._last_login = 0.0
        # Set once Weathercloud rejects the credentials; login is not tried
        # again until the entry is reloaded (new password, or a restart), so
        # a wrong password is not hammered every poll.
        self.auth_rejected = False

        # Redirects must stay visible: a 302 is how login success and an
        # expired session show up.
        self._http.follow_redirects = False
        # The SDK leaves timeouts to the client; httpx's own default is 5 s.
        self._http.timeout = httpx.Timeout(DEFAULT_TIMEOUT)
        self._http.headers["User-Agent"] = _USER_AGENT
        self._http.headers["Accept"] = "application/json"
        self._client = AsyncWeathercloudClient(
            base_url=self._base_url,
            requested_with="XMLHttpRequest",
            httpx_client=self._http,
        )

    @property
    def has_credentials(self) -> bool:
        return bool(self._username and self._password)

    @property
    def device_id(self) -> str:
        return self._device_id

    def diagnostics(self) -> dict[str, Any]:
        """Session state for the diagnostics download (no secrets)."""
        return {
            "has_credentials": self.has_credentials,
            "logged_in": self._logged_in,
            "auth_rejected": self.auth_rejected,
            "indoor_seen": self._had_indoor,
            "metar_station": bool(_ICAO_RE.match(self._device_id)),
            "timeout_s": DEFAULT_TIMEOUT,
        }

    async def async_close(self) -> None:
        await self._http.aclose()

    # --- auth -------------------------------------------------------------
    async def async_login(self) -> None:
        """Log in so the station owner's indoor sensors are included.

        Raises WeathercloudAuthError on bad credentials and WeathercloudApiError
        when Weathercloud cannot be reached.
        """
        if not self.has_credentials:
            raise WeathercloudAuthError("No username/password configured")

        try:
            # Prime the session cookies, as the web form expects.
            await self._http.get(
                f"{self._base_url}/",
                headers={"Accept": "text/html"},
                timeout=DEFAULT_TIMEOUT,
            )
            resp = await self._http.post(
                f"{self._base_url}/signin",
                data={
                    "LoginForm[entity]": self._username,
                    "LoginForm[password]": self._password,
                    "LoginForm[rememberMe]": "1",
                },
                headers={"Accept": "text/html"},
                timeout=DEFAULT_TIMEOUT,
            )
        except httpx.HTTPError as err:
            raise WeathercloudApiError(f"Login request failed: {err}") from err

        self._last_login = time.monotonic()
        location = resp.headers.get("location", "")
        if resp.status_code != 302 or "signin" in location:
            self._logged_in = False
            self.auth_rejected = True
            # Drop any old session cookie, so the public readings keep
            # working without it.
            self._http.cookies.clear()
            raise WeathercloudAuthError(
                f"Login rejected (status {resp.status_code})"
            )
        self._logged_in = True
        self.auth_rejected = False

    async def _async_try_login(self) -> None:
        """Log in, but never let a login problem block the public readings."""
        if self.auth_rejected:
            return
        try:
            await self.async_login()
        except WeathercloudAuthError as err:
            _LOGGER.warning(
                "Weathercloud login failed, continuing without indoor sensors: %s",
                err,
            )
        except WeathercloudApiError as err:
            _LOGGER.debug("Weathercloud login not possible right now: %s", err)

    # --- station facts ----------------------------------------------------
    async def async_get_station_info(self) -> StationInfo:
        """Name, city, altitude and position of the station.

        Two requests (the JSON info endpoint and the public station page);
        either may fail on its own, and whatever was found is returned.
        Raises WeathercloudApiError only when both fail.
        """
        if _ICAO_RE.match(self._device_id):
            return StationInfo(name=self._device_id)

        city = altitude = None
        name = lat = lon = None
        failures = 0

        try:
            info = await self._client.device_live.get_info(device_id=self._device_id)
            device = getattr(info, "device", None)
            city = (getattr(device, "city", None) or None) if device else None
            altitude = _float(getattr(device, "altitude", None)) if device else None
        except (ApiError, ParsingError, httpx.HTTPError) as err:
            failures += 1
            _LOGGER.debug("Weathercloud station info unavailable: %s", err)

        try:
            html = await self._client.stations.get_station_page(
                device_id=self._device_id,
                request_options={"additional_headers": {"Accept": "text/html"}},
            )
            if isinstance(html, str):
                name, lat, lon = parse_station_page(html)
        except (ApiError, ParsingError, httpx.HTTPError) as err:
            failures += 1
            _LOGGER.debug("Weathercloud station page unavailable: %s", err)

        if failures == 2:
            raise WeathercloudApiError("Station info and page both unavailable")
        return StationInfo(name, city, altitude, lat, lon)

    # --- data -------------------------------------------------------------
    async def _async_fetch(self) -> Any:
        if _ICAO_RE.match(self._device_id):
            return await self._client.metar.get_values(device_id=self._device_id)
        return await self._client.device_live.get_values(device_id=self._device_id)

    async def async_get_values(self) -> Any:
        """Return the station's latest readings (a ``DeviceValues`` model).

        Field names are Weathercloud's own: ``temp``, ``hum``, ``bar``, ``wspd``
        and so on. Wind is in m/s, pressure in hPa.
        """
        if self.has_credentials and not self._logged_in:
            await self._async_try_login()

        try:
            values = await self._async_fetch()
        except ApiError as err:
            if not (self.has_credentials and err.status_code in _AUTH_STATUSES):
                raise WeathercloudApiError(f"Weathercloud API error: {err}") from err
            # Session expired: log in again once and retry.
            _LOGGER.debug("Weathercloud session expired (%s), logging in again", err.status_code)
            self._logged_in = False
            await self._async_try_login()
            values = await self._async_fetch_or_raise()
        except ParsingError as err:
            raise WeathercloudApiError(f"Unexpected Weathercloud response: {err}") from err
        except httpx.HTTPError as err:
            raise WeathercloudApiError(f"Weathercloud request failed: {err}") from err

        if self.has_credentials:
            values = await self._async_check_indoor(values)
        return values

    async def _async_fetch_or_raise(self) -> Any:
        try:
            return await self._async_fetch()
        except (ApiError, ParsingError) as err:
            raise WeathercloudApiError(f"Weathercloud API error: {err}") from err
        except httpx.HTTPError as err:
            raise WeathercloudApiError(f"Weathercloud request failed: {err}") from err

    async def _async_check_indoor(self, values: Any) -> Any:
        """Some expired sessions still get 200 with the public values only.

        If indoor readings were there before and disappeared, log in again
        (rate limited) and fetch once more.
        """
        has_indoor = any(getattr(values, f, None) is not None for f in INDOOR_FIELDS)
        if has_indoor:
            self._had_indoor = True
            return values
        if not self._had_indoor:
            return values
        if time.monotonic() - self._last_login < _RELOGIN_COOLDOWN:
            return values

        _LOGGER.debug("Indoor readings disappeared, refreshing Weathercloud login")
        self._logged_in = False
        await self._async_try_login()
        try:
            return await self._async_fetch_or_raise()
        except WeathercloudApiError:
            return values
