"""Tests for the Weathercloud wrapper, against a fake Weathercloud server.

The wrapper has no Home Assistant imports, so it is loaded straight from its
file; this keeps the tests independent of a Home Assistant install.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "ims_weathercloud"

_spec = importlib.util.spec_from_file_location(
    "ims_wc_weathercloud_api", INTEGRATION / "weathercloud_api.py"
)
api_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = api_mod
_spec.loader.exec_module(api_mod)

WeathercloudApi = api_mod.WeathercloudApi
WeathercloudApiError = api_mod.WeathercloudApiError
WeathercloudAuthError = api_mod.WeathercloudAuthError

DEVICE = "3930075612"
PUBLIC = {
    "epoch": 1792900000, "temp": 21.4, "hum": 63, "bar": 1013.2, "dew": 14.1,
    "heat": 21.6, "wdir": 270, "wdiravg": 265, "wspd": 3.1, "wspdavg": 2.4,
    "wspdhi": 6.2, "rain": 1.2, "rainrate": 0.0, "solarrad": 412.0, "uvi": 3.4,
}
INDOOR = {"tempin": 24.0, "humin": 48, "heatin": 24.1}
STATION_PAGE = (
    "<html><head><title>Rooftop Ramat Aviv - Weathercloud | Global network"
    "</title></head><body><script>var latitude = 32.1133;\n"
    "var longitude = 34.8044;</script></body></html>"
)


class FakeWeathercloud:
    """Just enough of app.weathercloud.net to exercise the wrapper."""

    def __init__(self, password: str = "secret") -> None:
        self.password = password
        self.sessions: set[str] = set()
        self.logins = 0
        self.value_calls = 0
        self.expire_with_redirect = False
        self.fail_values_with: int | None = None
        self.paths: list[str] = []
        self.fail_info = False
        self.fail_page = False
        self.page_html = STATION_PAGE

    def expire_all(self) -> None:
        self.sessions.clear()

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.paths.append(path)
        sid = request.headers.get("cookie", "")
        sid = re.search(r"sid=(\w+)", sid).group(1) if "sid=" in sid else None

        if path == "/" and request.method == "GET":
            return httpx.Response(200, text="<html>home</html>",
                                  headers={"set-cookie": "csrf=1; Path=/"})

        if path == "/signin" and request.method == "POST":
            self.logins += 1
            form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
            if form.get("LoginForm%5Bpassword%5D") == self.password:
                new = f"s{self.logins}"
                self.sessions.add(new)
                return httpx.Response(302, headers={
                    "location": "/", "set-cookie": f"sid={new}; Path=/"})
            return httpx.Response(200, text="<form>LoginForm invalid</form>")

        if path.startswith("/device/info/"):
            if self.fail_info:
                return httpx.Response(500, text="boom")
            return httpx.Response(200, json={
                "device": {"city": "Tel Aviv-Yafo", "altitude": "35", "status": "1"}})

        if re.fullmatch(r"/d\d+", path):
            if self.fail_page:
                return httpx.Response(503, text="down")
            return httpx.Response(200, text=self.page_html,
                                  headers={"content-type": "text/html"})

        if path.startswith(("/device/values/", "/metar/values/")):
            self.value_calls += 1
            if self.fail_values_with:
                return httpx.Response(self.fail_values_with, text="boom")
            assert request.headers.get("x-requested-with") == "XMLHttpRequest"
            logged_in = sid in self.sessions
            if sid and not logged_in and self.expire_with_redirect:
                return httpx.Response(302, headers={"location": "/signin"})
            body = dict(PUBLIC)
            if logged_in:
                body.update(INDOOR)
            return httpx.Response(200, json=body)

        return httpx.Response(404)


def make_api(server: FakeWeathercloud, device=DEVICE, user=None, pw=None):
    http = httpx.AsyncClient(transport=httpx.MockTransport(server.handler))
    return WeathercloudApi(http, device, user, pw)


async def test_public_values():
    server = FakeWeathercloud()
    api = make_api(server)
    values = await api.async_get_values()
    assert values.temp == 21.4 and values.wspd == 3.1 and values.bar == 1013.2
    assert values.tempin is None
    assert server.logins == 0
    await api.async_close()


async def test_login_once_and_indoor_values():
    server = FakeWeathercloud()
    api = make_api(server, user="me", pw="secret")
    first = await api.async_get_values()
    second = await api.async_get_values()
    assert first.tempin == 24.0 and second.humin == 48
    # 0.1.x logged in on every poll; the session is now reused.
    assert server.logins == 1
    await api.async_close()


async def test_bad_password_keeps_public_data(caplog):
    server = FakeWeathercloud()
    api = make_api(server, user="me", pw="wrong")
    values = await api.async_get_values()
    assert values.temp == 21.4 and values.tempin is None
    assert "login failed" in caplog.text.lower()
    with pytest.raises(WeathercloudAuthError):
        await api.async_login()
    await api.async_close()


async def test_expired_session_redirect_relogs_in():
    server = FakeWeathercloud()
    server.expire_with_redirect = True
    api = make_api(server, user="me", pw="secret")
    await api.async_get_values()
    server.expire_all()
    values = await api.async_get_values()
    assert values.tempin == 24.0
    assert server.logins == 2
    await api.async_close()


async def test_indoor_vanish_relogin_is_rate_limited(monkeypatch):
    server = FakeWeathercloud()
    api = make_api(server, user="me", pw="secret")
    clock = [1000.0]
    monkeypatch.setattr(api_mod.time, "monotonic", lambda: clock[0])

    assert (await api.async_get_values()).tempin == 24.0
    server.expire_all()  # server now silently serves public data only

    # Within the cooldown: no new login, public values are returned.
    clock[0] += 60
    assert (await api.async_get_values()).tempin is None
    assert server.logins == 1

    # After the cooldown: one new login, indoor values are back.
    clock[0] += 3600
    assert (await api.async_get_values()).tempin == 24.0
    assert server.logins == 2
    await api.async_close()


async def test_station_without_indoor_never_relogs():
    server = FakeWeathercloud()
    api = make_api(server, user="me", pw="secret")
    original = dict(INDOOR)
    INDOOR.clear()
    try:
        for _ in range(3):
            await api.async_get_values()
    finally:
        INDOOR.update(original)
    assert server.logins == 1
    await api.async_close()


@pytest.mark.parametrize("status", [404, 500])
async def test_http_errors_raise(status):
    server = FakeWeathercloud()
    server.fail_values_with = status
    api = make_api(server)
    with pytest.raises(WeathercloudApiError):
        await api.async_get_values()
    await api.async_close()


async def test_timeout_matches_old_library():
    api = make_api(FakeWeathercloud())
    assert api._http.timeout.read == 10.0
    await api.async_close()


async def test_icao_uses_metar_endpoint():
    server = FakeWeathercloud()
    api = make_api(server, device="LLBG")
    await api.async_get_values()
    assert "/metar/values/LLBG" in server.paths
    await api.async_close()


def test_coordinator_reads_only_known_fields():
    """Every Weathercloud field the coordinator reads must exist in the SDK model."""
    from weathercloud.types import DeviceValues

    source = (INTEGRATION / "coordinator.py").read_text(encoding="utf-8")
    used = set(re.findall(r'getattr\(wc, "(\w+)"', source))
    assert used, "no Weathercloud fields found in coordinator.py"
    # pydantic v2 exposes model_fields; v1 (older Home Assistant) __fields__.
    known = getattr(DeviceValues, "model_fields", None) or DeviceValues.__fields__
    unknown = used - set(known)
    assert not unknown, f"fields not in weathercloud.DeviceValues: {sorted(unknown)}"


async def test_rejected_password_is_not_retried_every_poll():
    server = FakeWeathercloud()
    api = make_api(server, user="me", pw="wrong")
    for _ in range(3):
        values = await api.async_get_values()
        assert values.temp == 21.4
    assert api.auth_rejected
    assert server.logins == 1
    await api.async_close()


async def test_password_changed_on_site_keeps_public_data():
    server = FakeWeathercloud()
    server.expire_with_redirect = True
    api = make_api(server, user="me", pw="secret")
    assert (await api.async_get_values()).tempin == 24.0

    # Password changed on weathercloud.net: session dies, login now fails.
    server.password = "changed"
    server.expire_all()
    values = await api.async_get_values()
    assert values.temp == 21.4 and values.tempin is None
    assert api.auth_rejected
    # Next polls: no login attempts, public data still served.
    assert (await api.async_get_values()).temp == 21.4
    assert server.logins == 2
    await api.async_close()


def test_diagnostics_has_no_secrets():
    api = make_api(FakeWeathercloud(), user="me@example.com", pw="secret")
    diag = api.diagnostics()
    assert "secret" not in str(diag) and "me@example.com" not in str(diag)
    assert diag["has_credentials"] is True



# --- station details ------------------------------------------------------
@pytest.mark.parametrize(
    ("html", "expected"),
    [
        (STATION_PAGE, ("Rooftop Ramat Aviv", 32.1133, 34.8044)),
        ("<title>X - Weathercloud</title>var latitude = -33.9;var longitude = 151.2;",
         ("X", -33.9, 151.2)),
        ("<title>Y - Weathercloud</title>var latitude = 0;var longitude = 0;", ("Y", None, None)),
        ("<title>Z</title>var latitude = 123;var longitude = 34;", ("Z", None, None)),
        ("<html>no data</html>", (None, None, None)),
    ],
)
def test_parse_station_page(html, expected):
    assert api_mod.parse_station_page(html) == expected


async def test_station_info():
    server = FakeWeathercloud()
    api = make_api(server)
    info = await api.async_get_station_info()
    assert info == api_mod.StationInfo(
        name="Rooftop Ramat Aviv", city="Tel Aviv-Yafo", altitude=35.0,
        latitude=32.1133, longitude=34.8044,
    )
    await api.async_close()


async def test_station_info_partial_and_total_failure():
    server = FakeWeathercloud()
    server.fail_page = True
    api = make_api(server)
    info = await api.async_get_station_info()
    assert info.city == "Tel Aviv-Yafo" and info.latitude is None

    server.fail_info = True
    with pytest.raises(WeathercloudApiError):
        await api.async_get_station_info()
    await api.async_close()


async def test_station_info_for_metar_needs_no_requests():
    server = FakeWeathercloud()
    api = make_api(server, device="LLBG")
    info = await api.async_get_station_info()
    assert info.name == "LLBG" and server.paths == []
    await api.async_close()
