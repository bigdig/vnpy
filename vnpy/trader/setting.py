"""
Global setting of VN Trader.
"""

from logging import CRITICAL

from .utility import load_json

SETTINGS = {
    "font.family": "Arial",
    "font.size": 12,

    "log.active": True,
    "log.level": CRITICAL,
    "log.console": True,
    "log.file": True,

    "email.server": "smtp.qq.com",
    "email.port": 465,
    "email.username": "",
    "email.password": "",
    "email.sender": "",
    "email.receiver": "",

    "rqdata.username": "license",
    "rqdata.password": "Gxcn2mv3gtQ0uvOVQro09Otlp865PM9OocwyEx7uRbdWYg1CjlaEVofvsHzrZkVAdmeE7pynzxfiYwKZbgtcLaB4I7xDTlhRaSYrissoSgRwlEXDnA5u_c9LEdHGiV2RmhkOJLO-Y7ota0U8haAuRIvWFQEPWEaTbKfatNtjmKI=XNW1WAN4wHYmVfAeyHeT3h46CY89_dUVmtEP8lMyosFE5IQLsRJmXLjISrNWwwq1KhcBNIHAcG9EJy5AY27VJE9ULFH_95wLSYWBDnKKYmulrtapSZoJljOlJPXUjPU1NrPpmP0NhazGXJesNhlqoS371SfT75YHktASIIv2q6k=",

    "database.driver": "sqlite",  # see database.Driver
    "database.database": "database.db",  # for sqlite, use this as filepath
    "database.host": "localhost",
    "database.port": 3306,
    "database.user": "root",
    "database.password": "",
    "database.authentication_source": "admin",  # for mongodb
}

# Load global setting from json file.
SETTING_FILENAME = "vt_setting.json"
SETTINGS.update(load_json(SETTING_FILENAME))


def get_settings(prefix: str = ""):
    prefix_length = len(prefix)
    return {k[prefix_length:]: v for k, v in SETTINGS.items() if k.startswith(prefix)}
