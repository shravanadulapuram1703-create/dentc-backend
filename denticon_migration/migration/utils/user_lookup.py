"""Resolve Denticon USERID strings to users.id after migration seeding."""


def build_user_lookup(conn) -> dict[str, int]:
    """Map legacy_id / username (any case) → users.id."""
    cur = conn.cursor()
    cur.execute("SELECT id, legacy_id, username FROM users")
    lookup: dict[str, int] = {}
    for user_id, legacy_id, username in cur.fetchall():
        for key in (legacy_id, username):
            if key:
                lookup[key] = user_id
                lookup[key.lower()] = user_id
    return lookup


def resolve_user_id(lookup: dict[str, int], userid: str) -> int | None:
    userid = (userid or "").strip()
    if not userid:
        return None
    return lookup.get(userid) or lookup.get(userid.lower())
