"""
Provide computer status info.

To get network upload and download speeds, speedtest-cli app should be installed
"""

#!/usr/bin/env python
import operator
import os
import threading
import time
from collections import deque
from pprint import pprint
from typing import Optional

import psutil
import platform

from stream2py import SourceReader
from stream2py.utility.typing_hints import ComparableType, Any

__all__ = ["StatusInfo", "StatusInfoReader"]

DFLT_STATUS_INFO_READ_INTERVAL = 1000  # in ms
# How long `StatusInfoReader.open()` waits for the previous run's worker thread
# to stop before starting a new one. `None` means wait for as long as it takes.
DFLT_REOPEN_TIMEOUT_S = None


class StatusInfo:
    SPEEDTEST_CMD = "speedtest"

    @staticmethod
    def disk_free_bytes(path: str = "/") -> dict:
        return {"val": int(psutil.disk_usage(path).free), "unit": "bytes"}

    @staticmethod
    def disk_used_percents(path: str = "/") -> dict:
        return {"val": float(psutil.disk_usage(path).percent), "unit": "%"}

    @staticmethod
    def cpu_used_percents():
        return {"val": psutil.cpu_percent(), "unit": "%"}

    @staticmethod
    def cpu_temp():

        _t = -1
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as ftemp:
                _t = ftemp.readline()
                _t = float(int(_t) / 1000)
        except Exception as ex:
            _t = -1

        return {"val": _t, "unit": "C"}

    @staticmethod
    def mem_total():
        """
        - total:
          total physical memory available.
        """
        return {"val": psutil.virtual_memory().total, "unit": "bytes"}

    @staticmethod
    def mem_available():
        """
        - available:
          the memory that can be given instantly to processes without the
          system going into swap.
          This is calculated by summing different memory values depending
          on the platform and it is supposed to be used to monitor actual
          memory usage in a cross platform fashion.
        """
        return {"val": psutil.virtual_memory().available, "unit": "bytes"}

    @staticmethod
    def mem_used_percent():
        """
        - used:
          the percentage usage calculated as (total - available) / total * 100
        """
        return {"val": psutil.virtual_memory().percent, "unit": "%"}

    @staticmethod
    def mem_used_bytes():
        """
        - used:
           memory used, calculated differently depending on the platform and
           designed for informational purposes only:
           macOS: active + wired
           BSD: active + wired + cached
           Linux: total - free
        """
        return {"val": psutil.virtual_memory().used, "unit": "bytes"}

    @staticmethod
    def mem_free():
        """
        - free:
          memory not being used at all (zeroed) that is readily available;
          note that this doesn't reflect the actual memory available
          (use 'available' instead)

        """
        return {"val": psutil.virtual_memory().free, "unit": "bytes"}

    @staticmethod
    def platform():
        _info = platform.uname()
        if _info is None or len(_info._fields) == 0:
            return {"val": None, "unit": None}

        _values = dict()
        for _f in _info._fields:
            _values[_f] = _info.__getattribute__(_f)
        return {"val": _values, "unit": "json"}

    @staticmethod
    def network_download_speed() -> Optional[dict]:
        """
            Method to get download speed by testing real network speed.
            It requires speedtest python  system app to be installed.

            WARNING: The method is very slow
        :return:
        """
        try:
            with os.popen(
                StatusInfo.SPEEDTEST_CMD + " --no-upload --simple "
            ) as speedtest_output:
                for line in speedtest_output:
                    label, value, unit = line.split()
                    if "download" in label.lower():
                        return {"val": float(value), "unit": unit}
        except Exception as ex:
            return {"val": float(0), "unit": "not installed"}

    @staticmethod
    def network_upload_speed() -> dict:
        """
            Method to get upload speed by testing real network speed.
            It requires speedtest python  system app to be installed.

            WARNING: The method is very slow
        :return:
        """
        try:
            with os.popen(
                StatusInfo.SPEEDTEST_CMD + " --no-download --simple "
            ) as speedtest_output:
                for line in speedtest_output:
                    label, value, unit = line.split()
                    if "upload" in label.lower():
                        return {"val": float(value), "unit": unit}
        except Exception as ex:
            return {"val": float(0), "unit": "not installed"}

    @staticmethod
    def all(
        include_network_download_speed: bool = False,
        include_network_upload_speed: bool = False,
    ):

        _info = {
            "memory": {
                "total": StatusInfo.mem_total(),
                "available": StatusInfo.mem_available(),
                "free": StatusInfo.mem_free(),
                "used_bytes": StatusInfo.mem_used_bytes(),
                "used_percents": StatusInfo.mem_used_percent(),
            },
            "disk": {
                "free": StatusInfo.disk_free_bytes(),
                "used": StatusInfo.disk_used_percents(),
            },
            "cpu": {
                "used": StatusInfo.cpu_used_percents(),
                "temp": StatusInfo.cpu_temp(),
            },
            "platform": StatusInfo.platform(),
        }

        if include_network_download_speed or include_network_upload_speed:
            _info["network"] = dict()

        if include_network_download_speed:
            _info["network"]["download"] = StatusInfo.network_download_speed()

        if include_network_upload_speed:
            _info["network"]["upload"] = StatusInfo.network_upload_speed()

        return _info


_ITEMGETTER_0 = operator.itemgetter(0)


class SyncQueue:
    def __init__(self):
        self.lock = threading.Lock()
        self.queue = deque()

    def len(self):
        with self.lock:
            return len(self.queue)

    def popleft(self):
        with self.lock:
            return self.queue.popleft()

    def popleft_no_block(self):
        with self.lock:
            if len(self.queue):
                return self.queue.popleft()

    def clear(self):
        with self.lock:
            return self.queue.clear()

    def append(self, item):
        with self.lock:
            return self.queue.append(item)


class StatusInfoReader(SourceReader, threading.Thread):
    def __init__(
        self,
        read_interval_ms=DFLT_STATUS_INFO_READ_INTERVAL,
        include_network_download_speed: bool = False,
        include_network_upload_speed: bool = False,
        *,
        reopen_timeout_s: Optional[float] = DFLT_REOPEN_TIMEOUT_S,
    ):

        threading.Thread.__init__(self, daemon=True)

        self.read_interval_ms = read_interval_ms
        self.include_network_download_speed = include_network_download_speed
        self.include_network_upload_speed = include_network_upload_speed
        self.reopen_timeout_s = reopen_timeout_s

        # Per-instance state. These used to be *class* attributes, which meant
        # every StatusInfoReader shared one queue and one stop flag.
        self._index: int = 0
        self._data: SyncQueue = SyncQueue()
        self._bt: Optional[int] = None
        # Deliberately NOT named `_stop`: `threading.Thread._stop` is a method
        # CPython calls internally (from `_wait_for_tstate_lock`, reached via
        # `join()` and `is_alive()`), so shadowing it with an Event breaks
        # `join()` with "TypeError: 'Event' object is not callable".
        self._stop_event: threading.Event = threading.Event()
        # The thread currently running `run`, or None while the reader has never
        # been opened (see `_start_worker`).
        self._worker: Optional[threading.Thread] = None

    def open(self):
        """Start reading status info in the background.

        Can be called again after `close()`: a reader is reusable, as
        `SourceReader`'s reuse contract requires. Each call stops and waits for
        the worker started by the previous call, so exactly one thread feeds
        the queue at a time.
        """
        self._stop_previous_worker()

        self._data.clear()
        self._bt = self.get_timestamp()
        self._index = 0

        self._stop_event.clear()
        self._start_worker()

    def _stop_previous_worker(self):
        """Signal and wait for the worker started by an earlier `open()`, if any.

        Waiting is required, not cosmetic: `open()` clears the stop flag, and a
        previous worker still inside its `time.sleep` would never observe the
        stop, leaving two threads appending to the same queue.
        """
        worker = self._worker
        if worker is None and threading.Thread.is_alive(self):
            # Started the legacy way (`start()`, so running in `self`) and then
            # `open()`ed: that run must stop too, or it would miss the stop flag
            # `open()` clears below and keep feeding the queue next to the new one.
            worker = self
        if worker is None or not worker.is_alive():
            return

        self._stop_event.set()
        worker.join(self.reopen_timeout_s)
        if worker.is_alive():
            raise RuntimeError(
                f"{type(self).__name__}.open(): the worker thread of the previous"
                f" run did not stop within reopen_timeout_s={self.reopen_timeout_s}"
                f" seconds, so a new one can't be started without ending up with"
                f" two producers feeding the same queue. Give the reader a longer"
                f" reopen_timeout_s (or None to wait for as long as it takes)."
            )

    def _start_worker(self):
        """Run `run` in a fresh daemon thread: one per `open()`.

        A `threading.Thread` can only be started once, so a reusable reader
        can't run its work in `self` -- not even the first time, or `self` would
        be a finished thread standing in for the reader from the second `open()`
        on. `is_alive()` and `join()` are overridden to follow the current
        worker, so they keep meaning "is it reading" and "wait for it to stop".
        """
        self._worker = threading.Thread(
            target=self.run, daemon=True, name=f"{self.name}-worker"
        )
        self._worker.start()

    def _current_worker_is_another_thread(self) -> bool:
        worker = self._worker
        return worker is not None and worker is not self

    def is_alive(self) -> bool:
        """Whether the reader is currently reading, whichever thread is doing it.

        The work runs in a per-`open()` worker thread (see `_start_worker`), not
        in `self`, so the inherited `Thread.is_alive` would describe the wrong
        thread. (A reader started the legacy way, with `start()` rather than
        `open()`, has no worker and answers for `self` as before.)
        """
        if self._current_worker_is_another_thread():
            return self._worker.is_alive()
        return super().is_alive()

    def join(self, timeout: Optional[float] = None) -> None:
        """Wait for the current run's worker thread to finish (see `is_alive`)."""
        if self._current_worker_is_another_thread():
            return self._worker.join(timeout)
        return super().join(timeout)

    def read(self):
        """Returns one data item

        :return: (index, timestamp, character)
        """
        return self._data.popleft_no_block()

    def close(self):
        self._stop_event.set()

    @property
    def info(self) -> dict:
        return {"bt": self._bt}

    def key(self, data: Any) -> ComparableType:
        """
        :param data: (index, timestamp, character)
        :return: index
        """
        return _ITEMGETTER_0(data)

    def run(self):
        try:
            while not self._stop_event.is_set():
                self._data.append(
                    (
                        self._index,
                        self.get_timestamp(),
                        StatusInfo.all(
                            self.include_network_download_speed,
                            self.include_network_upload_speed,
                        ),
                    )
                )  # (index, timestamp, character)
                self._index += 1
                if self.read_interval_ms > 0:
                    time.sleep(self.read_interval_ms / 1000)

        except Exception:
            self.close()
            raise


def main():
    with StatusInfoReader() as source:
        print("Ctrl+C to exit")
        time.sleep(3)
        while True:
            try:
                data = source.read()
                if data is not None:
                    index, timestamp, info = data
                    pprint(f"{index}.{timestamp}: {info}")

            except KeyboardInterrupt as kb:
                break

    print("Done!")


if __name__ == "__main__":
    main()
    # As separated info
    # print(f"Memory:\n---------------------------------")
    # print(f"\tmem total {StatusInfo.mem_total()}")
    # print(f"\tmem available {StatusInfo.mem_available()}")
    # print(f"\tmem free {StatusInfo.mem_free()}")
    # print(f"\tmem used bytes {StatusInfo.mem_used_bytes()}")
    # print(f"\tmem used percents {StatusInfo.mem_used_percent()}")
    #
    # print(f"\nDisk:\n---------------------------------")
    # print(f"\tdisk free {StatusInfo.disk_free_bytes()}")
    # print(f"\tdisk used {StatusInfo.disk_used_percents()}")
    #
    # print(f"\nCPU:\n---------------------------------")
    # print(f"\tcpu used {StatusInfo.cpu_used_percents()}")
    # print(f"\tcpu temp {StatusInfo.cpu_temp()}")
    #
    # print(f"\nPlatform:\n---------------------------------")
    # print(f"\tplatform info {StatusInfo.platform()}")
    #
    # print(f"\nNetwork:\n---------------------------------")
    # print(f"\tDownload speed {StatusInfo.network_download_speed()}")
    # print(f"\tUpload speed {StatusInfo.network_upload_speed()}")

    # or as a single JSON
    # print(StatusInfo.all(include_network_download_speed=True, include_network_upload_speed=True))
