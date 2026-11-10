# -*- coding: utf-8 -*-
"""„Сеанс на деня“ — подредба на новини, карикатура, филм и радио."""
import time

import content


def _day_seed():
    return int(time.strftime("%Y%m%d"))


def _pick(key, offset=0):
    result = content.archive_search(key, page=1, rows=24)
    items = result.get("items") or []
    if not items:
        return None
    index = (_day_seed() + offset) % len(items)
    return items[index]


def build():
    """Връща речник с елементите на сеанса; липсващите са None."""
    program = {"film": None, "cartoon": None, "news": [], "radio": None}
    try:
        program["news"] = content.load_news()[:5]
    except Exception:
        program["news"] = []
    try:
        program["film"] = _pick("features", 0)
    except Exception:
        program["film"] = None
    try:
        program["cartoon"] = _pick("cartoons", 7)
    except Exception:
        program["cartoon"] = None
    radio = content.sources().get("radio") or []
    program["radio"] = radio[0] if radio else None
    return program
