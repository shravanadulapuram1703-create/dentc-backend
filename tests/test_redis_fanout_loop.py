"""Regression tests for the messaging fan-out reader loop.

The bug: ``start()`` spawns the reader immediately, but nothing is subscribed
until the first WebSocket arrives. redis-py raises "pubsub connection not set"
from ``get_message()`` in that window, so the loop logged a warning and slept 1s
— for the entire life of any instance holding no sockets. Observed on Cloud Run
at ~2 lines/second, indefinitely.

Driven with ``asyncio.run`` rather than pytest-asyncio: the project has no async
tests and no such dependency, and these need no event-loop fixtures.
"""

from __future__ import annotations

import asyncio

from app.integrations.redis_pubsub import RedisFanout


class FakePubSub:
    """Mimics redis-py: get_message() raises until something is subscribed."""

    def __init__(self):
        self.channels: set[str] = set()
        self.get_message_calls = 0
        self.queue: list[dict] = []

    async def subscribe(self, channel):
        self.channels.add(channel)

    async def unsubscribe(self, channel):
        self.channels.discard(channel)

    async def get_message(self, ignore_subscribe_messages=True, timeout=5.0):
        self.get_message_calls += 1
        if not self.channels:
            raise RuntimeError(
                "pubsub connection not set: did you forget to call subscribe()"
                " or psubscribe()?"
            )
        if self.queue:
            return self.queue.pop(0)
        await asyncio.sleep(0.01)
        return None


def _fanout(pubsub, sink=None) -> RedisFanout:
    f = RedisFanout()
    f._pubsub = pubsub
    f._sink = sink
    f.available = True
    return f


async def _cancel(task) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def test_reader_does_not_spin_before_any_subscription():
    """The production bug itself: no subscribers must mean no polling."""
    ps = FakePubSub()

    async def main():
        f = _fanout(ps)
        task = asyncio.create_task(f._read_loop())
        await asyncio.sleep(0.15)  # the old loop would have polled ~150x by now
        await _cancel(task)

    asyncio.run(main())
    assert ps.get_message_calls == 0


def test_reader_starts_after_first_subscribe():
    ps = FakePubSub()
    before = {}

    async def main():
        f = _fanout(ps)
        task = asyncio.create_task(f._read_loop())
        await asyncio.sleep(0.05)
        before["calls"] = ps.get_message_calls
        await f.subscribe("msg:1:42")
        await asyncio.sleep(0.05)
        await _cancel(task)

    asyncio.run(main())
    assert before["calls"] == 0
    assert ps.get_message_calls > 0


def test_reader_parks_again_when_last_socket_leaves():
    ps = FakePubSub()
    marks = {}

    async def main():
        f = _fanout(ps)
        task = asyncio.create_task(f._read_loop())
        await f.subscribe("msg:1:42")
        await asyncio.sleep(0.05)
        await f.unsubscribe("msg:1:42")
        await asyncio.sleep(0.03)
        marks["idle"] = ps.get_message_calls
        await asyncio.sleep(0.15)
        await _cancel(task)

    asyncio.run(main())
    assert ps.get_message_calls == marks["idle"], "must re-park, not resume spinning"


def test_refcount_keeps_reader_awake_for_second_socket():
    ps = FakePubSub()
    marks = {}

    async def main():
        f = _fanout(ps)
        task = asyncio.create_task(f._read_loop())
        await f.subscribe("msg:1:42")
        await f.subscribe("msg:1:42")   # second tab, same user
        await f.unsubscribe("msg:1:42")  # one tab closes
        await asyncio.sleep(0.05)
        marks["before"] = ps.get_message_calls
        await asyncio.sleep(0.05)
        await _cancel(task)

    asyncio.run(main())
    assert ps.get_message_calls > marks["before"], "one socket still open"


def test_message_is_dispatched_to_sink():
    got: list[tuple[str, str]] = []

    async def sink(channel, data):
        got.append((channel, data))

    async def main():
        ps = FakePubSub()
        ps.queue.append({"channel": "msg:1:42", "data": '{"x":1}'})
        f = _fanout(ps, sink)
        task = asyncio.create_task(f._read_loop())
        await f.subscribe("msg:1:42")
        await asyncio.sleep(0.05)
        await _cancel(task)

    asyncio.run(main())
    assert got == [("msg:1:42", '{"x":1}')]


def test_persistent_failure_backs_off_instead_of_flooding(monkeypatch):
    """A real outage must not reproduce the same flood in another guise."""
    slept: list[float] = []

    class AlwaysFails(FakePubSub):
        async def get_message(self, ignore_subscribe_messages=True, timeout=5.0):
            self.get_message_calls += 1
            raise RuntimeError("connection lost")

    async def fake_sleep(sec):
        slept.append(sec)
        if len(slept) >= 7:  # break out once we've seen the curve
            raise asyncio.CancelledError

    async def main():
        ps = AlwaysFails()
        ps.channels.add("msg:1:42")
        f = _fanout(ps)
        f._has_subs.set()  # gate open: this is a genuine read failure
        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        try:
            await f._read_loop()
        except asyncio.CancelledError:
            pass

    asyncio.run(main())
    assert slept[0] == 1.0, "first retry should be prompt"
    assert slept[-1] > slept[0], "backoff must escalate, not stay at 1/sec"
    assert max(slept) <= 30.0, "and must be capped"
