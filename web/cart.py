"""Session cart of schematic ids for batch checkout."""

from __future__ import annotations

CART_SESSION_KEY = 'schematic_cart_ids'


def get_cart_ids(request) -> list[int]:
    """Return unique schematic pks stored in the browser session."""
    session = getattr(request, 'session', None)
    if session is None:
        return []
    ids: list[int] = []
    seen: set[int] = set()
    for raw in session.get(CART_SESSION_KEY) or []:
        try:
            pk = int(raw)
        except (TypeError, ValueError):
            continue
        if pk not in seen:
            seen.add(pk)
            ids.append(pk)
    return ids


def cart_count(request) -> int:
    return len(get_cart_ids(request))


def add_to_cart(request, schematic_id: int) -> list[int]:
    ids = get_cart_ids(request)
    pk = int(schematic_id)
    if pk not in ids:
        ids.append(pk)
        request.session[CART_SESSION_KEY] = ids
        request.session.modified = True
    return ids


def remove_from_cart(request, schematic_id: int) -> list[int]:
    pk = int(schematic_id)
    ids = [item for item in get_cart_ids(request) if item != pk]
    request.session[CART_SESSION_KEY] = ids
    request.session.modified = True
    return ids


def clear_cart(request) -> None:
    session = getattr(request, 'session', None)
    if session is None:
        return
    session.pop(CART_SESSION_KEY, None)
    session.modified = True
