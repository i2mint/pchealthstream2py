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
