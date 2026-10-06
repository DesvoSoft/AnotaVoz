import array
import math
import sys


def rms_level(data):
    """RMS of 16-bit little-endian PCM, normalised to 0..1."""
    n = len(data) // 2
    if n == 0:
        return 0.0
    samples = array.array("h")
    samples.frombytes(data[: n * 2])
    if sys.byteorder == "big":
        samples.byteswap()
    total = sum(s * s for s in samples)
    return min(1.0, math.sqrt(total / n) / 32768.0)
