"""Bounded, in-memory history for dashboard percentage readings."""
from collections import deque
import math
import time


def _percent(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if 0 <= value <= 100 and math.isfinite(value):
            return float(value)
    return None


class HardwareHistory:
    """Store timestamped samples; call from the UI thread only."""

    def __init__(self, max_samples=60, window_seconds=60, clock=time.monotonic):
        if type(max_samples) is not int or max_samples < 1:
            raise ValueError('max_samples must be a positive integer')
        if not math.isfinite(window_seconds) or window_seconds <= 0:
            raise ValueError('window_seconds must be positive and finite')
        self._samples = deque(maxlen=max_samples)
        self._window = window_seconds
        self._clock = clock

    def _prune(self, now):
        while self._samples and now - self._samples[0][0] >= self._window:
            self._samples.popleft()

    def append(self, cpu=None, ram=None, disk=None):
        now = self._clock()
        self._prune(now)
        self._samples.append((now, _percent(cpu), _percent(ram), _percent(disk)))

    def snapshot(self):
        """Return immutable rows: (monotonic timestamp, CPU, RAM, disk)."""
        self._prune(self._clock())
        return tuple(self._samples)

    def clear(self):
        self._samples.clear()
