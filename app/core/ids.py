"""UUIDv7 generation — time-sortable ids for messaging.

Python 3.11 has no ``uuid.uuid7`` (added in 3.14), so we implement RFC 9562 §5.7
here. The layout puts a 48-bit big-endian Unix-millisecond timestamp in the most
significant bytes, which means **byte-order == time-order**. That property is
load-bearing for the messaging module:

* Postgres compares ``uuid`` bytewise and SQLite compares the hex string, so
  ``ORDER BY id`` is chronological on both without a secondary sort key.
* Message history therefore uses plain keyset pagination (``WHERE id < :before``)
  instead of a ``(created_at, id)`` tuple comparison — see
  ``MESSAGING_BACKEND_REQUIREMENTS.md`` §17.

A monotonic counter guards against collisions inside the same millisecond so ids
minted in a tight loop still sort in creation order.
"""

from __future__ import annotations

import os
import threading
import time
import uuid

_lock = threading.Lock()
_last_ms = -1
_last_seq = 0

# 12 bits of sub-millisecond sequence live in rand_a (RFC 9562 "method 1").
_SEQ_MAX = 0xFFF


def uuid7() -> uuid.UUID:
    """Return a time-sortable UUIDv7."""
    global _last_ms, _last_seq

    with _lock:
        ms = int(time.time() * 1000)
        if ms == _last_ms:
            _last_seq += 1
            if _last_seq > _SEQ_MAX:
                # Sequence exhausted within this millisecond: borrow from the
                # next one rather than emitting an out-of-order id.
                ms = _last_ms + 1
                _last_ms = ms
                _last_seq = 0
        elif ms < _last_ms:
            # Clock stepped backwards (NTP): keep advancing so ids stay monotonic.
            ms = _last_ms
            _last_seq += 1
        else:
            _last_ms = ms
            _last_seq = 0
        seq = _last_seq

    rand_b = int.from_bytes(os.urandom(8), "big") & 0x3FFFFFFFFFFFFFFF

    value = (ms & 0xFFFFFFFFFFFF) << 80
    value |= 0x7 << 76  # version 7
    value |= (seq & _SEQ_MAX) << 64
    value |= 0b10 << 62  # RFC 4122 variant
    value |= rand_b

    return uuid.UUID(int=value)


__all__ = ["uuid7"]
