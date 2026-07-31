from __future__ import annotations

from homeassistant.components.weather import (
    ATTR_CONDITION_CLEAR_NIGHT,
    ATTR_CONDITION_CLOUDY,
    ATTR_CONDITION_EXCEPTIONAL,
    ATTR_CONDITION_FOG,
    ATTR_CONDITION_HAIL,
    ATTR_CONDITION_LIGHTNING_RAINY,
    ATTR_CONDITION_PARTLYCLOUDY,
    ATTR_CONDITION_POURING,
    ATTR_CONDITION_RAINY,
    ATTR_CONDITION_SNOWY,
    ATTR_CONDITION_SNOWY_RAINY,
    ATTR_CONDITION_SUNNY,
    ATTR_CONDITION_WINDY,
)

DOMAIN = "ims_weathercloud"
PLATFORMS = ["weather", "sensor"]

DEFAULT_NAME = "IMS + Weathercloud"

# --- Config keys ---------------------------------------------------------
CONF_CITY = "city"
CONF_LANGUAGE = "language"
CONF_WC_DEVICE_ID = "wc_device_id"
CONF_WC_USERNAME = "wc_username"
CONF_WC_PASSWORD = "wc_password"
CONF_IMS_INTERVAL = "ims_interval"
CONF_WC_INTERVAL = "wc_interval"

DEFAULT_LANGUAGE = "he"
DEFAULT_IMS_INTERVAL = 60
DEFAULT_WC_INTERVAL = 10
MIN_INTERVAL = 1

SOURCE_IMS = "ims"
SOURCE_WEATHERCLOUD = "weathercloud"

# weatheril reports wind in km/h, weathercloud in m/s -> normalise before merge.
MS_TO_KMH = 3.6

WEATHERCLOUD_STATION_URL = "https://app.weathercloud.net/d{device_id}"


def ims_site_url(language: str | None) -> str:
    """IMS site in the language the user picked (fallback link when no station)."""
    lang = "en" if str(language).lower().startswith("en") else "he"
    return f"https://ims.gov.il/{lang}"


# --- Wind direction: IMS reports an index (1-17), not degrees ------------
# Source: https://ims.gov.il/en/wind_directions  (mirrors the IMS component)
WIND_DIRECTIONS: dict[int | None, float | None] = {
    None: None, 0: None,
    1: 360.0, 2: 23.0, 3: 45.0, 4: 68.0, 5: 90.0, 6: 113.0, 7: 135.0, 8: 150.0,
    9: 180.0, 10: 203.0, 11: 225.0, 12: 248.0, 13: 270.0, 14: 293.0, 15: 315.0,
    16: 338.0, 17: 0.0,
}


def ims_wind_bearing(direction_id: object) -> float | None:
    """Map an IMS wind_direction_id index to degrees."""
    try:
        return WIND_DIRECTIONS.get(int(direction_id))
    except (TypeError, ValueError):
        return None


# --- IMS weather_code -> HA condition (mirrors the IMS component) ---------
WEATHER_CODE_TO_CONDITION: dict[str, str | None] = {
    "1010": ATTR_CONDITION_EXCEPTIONAL,
    "1020": ATTR_CONDITION_LIGHTNING_RAINY,
    "1060": ATTR_CONDITION_SNOWY,
    "1070": ATTR_CONDITION_SNOWY,
    "1080": ATTR_CONDITION_SNOWY_RAINY,
    "1140": ATTR_CONDITION_POURING,
    "1160": ATTR_CONDITION_FOG,
    "1220": ATTR_CONDITION_PARTLYCLOUDY,
    "1220-night": ATTR_CONDITION_PARTLYCLOUDY,
    "1230": ATTR_CONDITION_CLOUDY,
    "1250": ATTR_CONDITION_SUNNY,
    "1250-night": ATTR_CONDITION_CLEAR_NIGHT,
    "1260": ATTR_CONDITION_WINDY,
    "1270": ATTR_CONDITION_SUNNY,
    "1300": ATTR_CONDITION_HAIL,
    "1310": ATTR_CONDITION_SUNNY,
    "1320": ATTR_CONDITION_HAIL,
    "1510": ATTR_CONDITION_LIGHTNING_RAINY,
    "1520": ATTR_CONDITION_SNOWY,
    "1530": ATTR_CONDITION_RAINY,
    "1540": ATTR_CONDITION_RAINY,
    "1560": ATTR_CONDITION_RAINY,
    "1570": ATTR_CONDITION_EXCEPTIONAL,
    "1580": ATTR_CONDITION_EXCEPTIONAL,
    "1590": ATTR_CONDITION_EXCEPTIONAL,
}

_NIGHT_CODES = {"1220", "1250"}


def ims_condition(code: str | None, hour: int | None = None) -> str | None:
    """Translate an IMS weather_code to a HA condition string.

    At night (hour < 6 or > 20) the 1220/1250 codes map to their -night
    variant, matching the IMS component behaviour.
    """
    if code is None:
        return None
    key = str(code)
    if hour is not None and key in _NIGHT_CODES and (hour < 6 or hour > 20):
        key = f"{key}-night"
    return WEATHER_CODE_TO_CONDITION.get(key)


# --- IMS city list (code -> display name) --------------------------------
IMS_CITIES: dict[str, str] = {
    "1": "Jerusalem", "2": "Tel Aviv - Yafo", "3": "Haifa", "4": "Rishon le Zion",
    "5": "Petah Tiqva", "6": "Ashdod", "7": "Netania", "8": "Beer Sheva",
    "9": "Bnei Brak", "10": "Holon", "11": "Ramat Gan", "12": "Asheqelon",
    "13": "Rehovot", "14": "Bat Yam", "15": "Bet Shemesh", "16": "Kfar Sava",
    "17": "Herzliya", "18": "Hadera", "19": "Modiin", "20": "Ramla",
    "21": "Raanana", "22": "Modiin Illit", "23": "Rahat", "24": "Hod Hasharon",
    "25": "Givatayim", "26": "Kiryat Ata", "27": "Nahariya", "28": "Beitar Illit",
    "29": "Um al-Fahm", "30": "Kiryat Gat", "31": "Eilat", "32": "Rosh Haayin",
    "33": "Afula", "34": "Nes-Ziona", "35": "Akko", "36": "Elad",
    "37": "Ramat Hasharon", "38": "Karmiel", "39": "Yavneh", "40": "Tiberias",
    "41": "Tayibe", "42": "Kiryat Motzkin", "43": "Shfaram", "44": "Nof Hagalil",
    "45": "Kiryat Yam", "46": "Kiryat Bialik", "47": "Kiryat Ono", "48": "Maale Adumim",
    "49": "Or Yehuda", "50": "Zefat", "51": "Netivot", "52": "Dimona",
    "53": "Tamra", "54": "Sakhnin", "55": "Yehud", "56": "Baka al-Gharbiya",
    "57": "Ofakim", "58": "Givat Shmuel", "59": "Tira", "60": "Arad",
    "61": "Migdal Haemek", "62": "Sderot", "63": "Araba", "64": "Nesher",
    "65": "Kiryat Shmona", "66": "Yokneam Illit", "67": "Kafr Qassem", "68": "Kfar Yona",
    "69": "Qalansawa", "70": "Kiryat Malachi", "71": "Maalot-Tarshiha", "72": "Tirat Carmel",
    "73": "Ariel", "74": "Or Akiva", "75": "Bet Shean", "76": "Mizpe Ramon",
    "77": "Lod", "78": "Nazareth", "79": "Qazrin", "80": "En Gedi",
    "200": "Nimrod Fortress", "201": "Banias", "202": "Tel Dan", "203": "Snir Stream",
    "204": "Horshat Tal", "205": "Ayun Stream", "206": "Hula", "207": "Tel Hazor",
    "208": "Akhziv", "209": "Yehiam Fortress", "210": "Baram", "211": "Amud Stream",
    "212": "Korazim", "213": "Kfar Nahum", "214": "Majrase", "215": "Meshushim Stream",
    "216": "Yehudiya", "217": "Gamla", "218": "Kursi", "219": "Hamat Tiberias",
    "220": "Arbel", "221": "En Afek", "222": "Tzipori", "223": "Hai-Bar Carmel",
    "224": "Mount Carmel", "225": "Bet Shearim", "226": "Mishmar HaCarmel",
    "227": "Nahal Me'arot", "228": "Dor-HaBonim", "229": "Tel Megiddo",
    "230": "Kokhav HaYarden", "231": "Maayan Harod", "232": "Bet Alpha",
    "233": "Gan HaShlosha", "235": "Taninim Stream", "236": "Caesarea",
    "237": "Tel Dor", "238": "Mikhmoret Sea Turtle", "239": "Beit Yanai",
    "240": "Apollonia", "241": "Mekorot HaYarkon", "242": "Palmahim", "243": "Castel",
    "244": "En Hemed", "245": "City of David", "246": "Me'arat Soreq", "248": "Bet Guvrin",
    "249": "Sha'ar HaGai", "250": "Migdal Tsedek", "251": "Haniya Spring", "252": "Sebastia",
    "253": "Mount Gerizim", "254": "Nebi Samuel", "255": "En Prat", "256": "En Mabo'a",
    "257": "Qasr al-Yahud", "258": "Good Samaritan", "259": "Euthymius Monastery",
    "261": "Qumran", "262": "Enot Tsukim", "263": "Herodium", "264": "Tel Hebron",
    "267": "Masada", "268": "Tel Arad", "269": "Tel Beer Sheva", "270": "Eshkol",
    "271": "Mamshit", "272": "Shivta", "273": "Ben-Gurion's Tomb", "274": "En Avdat",
    "275": "Avdat", "277": "Hay-Bar Yotvata", "278": "Coral Beach",
}
