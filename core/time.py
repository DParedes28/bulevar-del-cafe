from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_bogota(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(BOGOTA)


def combine_bogota(day: date, clock: time) -> datetime:
    local = datetime.combine(day, clock, tzinfo=BOGOTA)
    return local.astimezone(timezone.utc)


def format_bogota(value: datetime) -> str:
    return to_bogota(value).strftime("%d/%m/%Y %H:%M")


_MESES = (
    "",
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def format_plazo(value: datetime) -> str:
    local = to_bogota(value)
    return f"{local.day} de {_MESES[local.month]} a las {local.strftime('%H:%M')}"
