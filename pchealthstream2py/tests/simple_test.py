"""Simple tests"""

from pchealthstream2py.pchealth import StatusInfoReader
import threading
import time
from pprint import pprint


def test_simple():
    with StatusInfoReader() as source:
        time.sleep(3)
        for i in range(2):
            try:
                data = source.read()
                if data is not None:
                    index, timestamp, info = data
                    pprint(f'{index}.{timestamp}: {info}')

            except KeyboardInterrupt as kb:
                break

    print('Done!')


def test_readers_do_not_share_state():
    """Two readers must not share their queue and stop flag.

    Regression test: these used to be class attributes, so opening a second
    reader cleared the first one's buffer and closing either stopped both.
    """
    first = StatusInfoReader(read_interval_ms=50)
    second = StatusInfoReader(read_interval_ms=50)

    assert first._data is not second._data
    assert first._stop_event is not second._stop_event


def test_stop_does_not_shadow_thread_internals():
    """`Thread._stop` must stay the method CPython calls internally.

    Regression test: the stop flag used to be named `_stop`, shadowing
    `threading.Thread._stop`, which made `join()` raise
    "TypeError: 'Event' object is not callable" and left `is_alive()`
    stuck on True after the worker had finished.
    """
    reader = StatusInfoReader(read_interval_ms=50)
    # (`Thread._stop` exists up to Python 3.12; 3.13 removed it.)
    assert not isinstance(getattr(reader, '_stop', None), threading.Event)

    reader.open()
    try:
        time.sleep(0.5)
    finally:
        reader.close()
    reader.join(timeout=10)
    assert not reader.is_alive()


def test_reader_can_be_reopened():
    """A reader must be usable again after `close()`.

    Regression test: `StatusInfoReader` is also a `threading.Thread`, and
    `open()` used to call `self.start()` unconditionally, so the second
    `open()` always raised "threads can only be started once" -- violating the
    reuse contract that `SourceReader`'s own class docstring demonstrates.

    The count assertion covers the other half of the bug: if `open()` restarts
    without joining the previous worker, that worker is still sleeping when the
    stop flag is cleared, so it never exits and each cycle adds another producer
    to the same queue (counts drift 9 / 18 / 27 instead of holding at 9).
    """
    read_interval_ms = 50
    reader = StatusInfoReader(read_interval_ms=read_interval_ms)

    counts = []
    for _ in range(3):
        with reader:
            time.sleep(10 * read_interval_ms / 1000)
        counts.append(reader._data.len())

    assert all(count > 0 for count in counts), counts
    # One producer per cycle, not one more on every cycle. A leaked producer
    # multiplies the count by the cycle number, so the ratio separates the bug
    # from ordinary scheduling jitter.
    assert max(counts) < 2 * min(counts), counts


def test_reopen_does_not_leak_worker_threads():
    """Reopening must leave exactly one live worker, not one more each time.

    The timing-free half of `test_reader_can_be_reopened`: it inspects the
    worker threads themselves rather than how much they produced.
    """
    reader = StatusInfoReader(read_interval_ms=50)
    workers = []

    for _ in range(3):
        with reader:
            time.sleep(0.2)
            workers.append(reader._worker)
            # Only the newest worker runs; `open()` joined the earlier ones.
            expected = [False] * (len(workers) - 1) + [True]
            assert [worker.is_alive() for worker in workers] == expected

    for worker in workers:
        worker.join(timeout=10)
        assert not worker.is_alive()


def test_thread_api_follows_the_current_worker_after_reopen():
    """`is_alive()` / `join()` must describe the run in progress, not the first one.

    #3 ran the first `open()` in `self` and later ones in fresh threads, so after
    a reopen the inherited `Thread.is_alive` answered False for a reader that was
    busy reading (it described the finished first-run thread), and `join()`
    returned at once instead of waiting for the worker to stop.
    """
    reader = StatusInfoReader(read_interval_ms=50)
    with reader:
        time.sleep(0.1)
    reader.join(timeout=10)

    reader.open()
    try:
        time.sleep(0.1)
        assert reader.is_alive()
    finally:
        reader.close()
    reader.join(timeout=10)
    assert not reader.is_alive()
    assert not reader._worker.is_alive()


def test_open_after_a_legacy_start_leaves_a_single_producer():
    """A reader started with `start()` (running in `self`), closed, then `open()`ed
    must not keep the legacy run going: `open()` clears the stop flag, so a run it
    didn't wait for would never see the stop and would keep feeding the queue."""
    reader = StatusInfoReader(read_interval_ms=50)
    reader.start()
    time.sleep(0.1)
    reader.close()
    reader.open()
    try:
        assert not threading.Thread.is_alive(reader)  # the legacy run has stopped
        assert reader.is_alive()  # and the new worker is reading
    finally:
        reader.close()
    reader.join(timeout=10)
