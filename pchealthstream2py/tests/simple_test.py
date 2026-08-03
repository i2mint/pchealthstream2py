"""Simple tests"""

from pchealthstream2py.pchealth import StatusInfoReader
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
    assert callable(reader._stop)

    reader.open()
    try:
        time.sleep(0.5)
    finally:
        reader.close()
    reader.join(timeout=10)
    assert not reader.is_alive()
