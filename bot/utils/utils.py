from datetime import datetime

import pytz

# Время админам показываем киевское: они читают его вместе со звонком клиенту,
# а API отдаёт UTC. Зона берётся из pytz — в образе бота нет системной tzdata.
KYIV_TZ = pytz.timezone("Europe/Kyiv")


def fmt_dt(value, fallback: str = "—") -> str:
    """ISO-строка из API → «30.08.2026 10:22» за київським часом."""
    if not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return fallback
    if parsed.tzinfo is None:
        parsed = pytz.utc.localize(parsed)
    return parsed.astimezone(KYIV_TZ).strftime("%d.%m.%Y %H:%M")


def to_major(money: int)->float:
    return money/100

def to_minor(money: int)->float:
    return money*100