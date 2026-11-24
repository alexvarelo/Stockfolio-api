import threading
import time

from app.core.cache import TTLCacheBackend


def test_get_or_set_single_flight_per_key():
    c = TTLCacheBackend(60)
    calls = []

    def factory():
        calls.append(1)
        time.sleep(0.1)
        return "v"

    out = []
    ts = [threading.Thread(target=lambda: out.append(c.get_or_set("k", factory))) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert out == ["v"] * 8 and len(calls) == 1
    assert c._key_locks == {}


def test_different_keys_do_not_block_and_errors_not_cached():
    c = TTLCacheBackend(60)

    def boom():
        raise ValueError("x")

    try:
        c.get_or_set("a", boom)
    except ValueError:
        pass
    assert c.get("a") is None and c.get_or_set("a", lambda: 1) == 1
    assert c.get_or_set("b", lambda: 2) == 2
