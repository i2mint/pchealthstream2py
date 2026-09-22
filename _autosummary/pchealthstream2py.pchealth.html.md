# pchealthstream2py.pchealth

Provide computer status info.

To get network upload and download speeds, speedtest-cli app should be installed

### Classes

| `StatusInfo`()                                                                             |    |
|--------------------------------------------------------------------------------------------|----|
| [`StatusInfoReader`](#pchealthstream2py.pchealth.StatusInfoReader)([read_interval_ms, ...]) |    |

### *class* pchealthstream2py.pchealth.StatusInfoReader(read_interval_ms=1000, include_network_download_speed=False, include_network_upload_speed=False, , reopen_timeout_s=None)

Bases: `SourceReader`, [`Thread`](https://docs.python.org/3/library/threading.html#threading.Thread)

#### close()

Close and clean up source reader.
Will be called when StreamBuffer stops or if an exception is raised during read and append
loop.

#### *property* info *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)*

A dict with important source info. Default can be init_kwargs and open timestamp.

This info will be available in BufferReader after SourceReader has opened but any changes
made between open and close are not guaranteed to be visible. Any continuous status updates
should be included with read data instead.

* **Returns:**
  dict

#### is_alive()

Whether the reader is currently reading, whichever thread is doing it.

The work runs in a per-`open()` worker thread (see `_start_worker`), not
in `self`, so the inherited `Thread.is_alive` would describe the wrong
thread. (A reader started the legacy way, with `start()` rather than
`open()`, has no worker and answers for `self` as before.)

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

#### join(timeout=None)

Wait for the current run’s worker thread to finish (see `is_alive`).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### key(data)

* **Parameters:**
  **data** ([`Any`](https://docs.python.org/3/library/typing.html#typing.Any)) – (index, timestamp, character)
* **Return type:**
  `ComparableType`
* **Returns:**
  index

#### open()

Start reading status info in the background.

Can be called again after `close()`: a reader is reusable, as
`SourceReader`’s reuse contract requires. Each call stops and waits for
the worker started by the previous call, so exactly one thread feeds
the queue at a time.

#### read()

Returns one data item

* **Returns:**
  (index, timestamp, character)

#### run()

Method representing the thread’s activity.

You may override this method in a subclass. The standard run() method
invokes the callable object passed to the object’s constructor as the
target argument, if any, with sequential and keyword arguments taken
from the args and kwargs arguments, respectively.
