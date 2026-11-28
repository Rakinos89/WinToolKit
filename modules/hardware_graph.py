"""Reusable, passive Tkinter percentage history graph."""
import math
import time
import tkinter as tk


def graph_segments(rows, metric, now, width, height, window=60):
    """Map timestamped history to contiguous pixel segments (no fake zeros)."""
    if metric not in (1, 2, 3) or window <= 0:
        raise ValueError('Invalid metric or time window')
    if width <= 0 or height <= 0:
        return []
    segments, current = [], []
    previous = None
    for row in rows:
        stamp, value = row[0], row[metric]
        if not now - window <= stamp <= now:
            continue
        valid = (isinstance(value, (int, float)) and not isinstance(value, bool)
                 and math.isfinite(value) and 0 <= value <= 100)
        if not valid or (previous is not None and stamp - previous > 2.5):
            if current:
                segments.append(current)
                current = []
        if valid:
            current.append(((stamp - now + window) / window * width,
                            (1 - value / 100) * height))
        previous = stamp
    if current:
        segments.append(current)
    return segments


class HardwareGraph(tk.Canvas):
    """Caller supplies samples and theme; no timers or worker threads."""

    def __init__(self, master, metric, accent='#299e77', background='#282828',
                 clock=time.monotonic, **kwargs):
        super().__init__(master, background=background, highlightthickness=0,
                         height=100, **kwargs)
        self.metric = metric
        self.accent = accent
        self.clock = clock
        self.rows = ()
        self.bind('<Configure>', self._redraw)

    def update_history(self, rows):
        self.rows = tuple(rows)
        self._redraw()

    def set_theme(self, accent, background=None):
        self.accent = accent
        if background is not None:
            self.configure(background=background)
        self._redraw()

    def _redraw(self, event=None):
        self.delete('all')
        w, h = self.winfo_width() - 2, self.winfo_height() - 2
        if w <= 0 or h <= 0:
            return
        for fraction in (0, .25, .5, .75, 1):
            y = 1 + h * fraction
            self.create_line(1, y, w + 1, y, fill='#454545', dash=(3, 3))
        bg = self.winfo_rgb(self.cget('background'))
        fg = self.winfo_rgb(self.accent)
        shade = '#%02x%02x%02x' % tuple(int((a * .82 + b * .18) / 257) for a, b in zip(bg, fg))
        for segment in graph_segments(self.rows, self.metric, self.clock(), w, h):
            points = [(x + 1, y + 1) for x, y in segment]
            if len(points) == 1:
                x, y = points[0]
                self.create_oval(x-2, y-2, x+2, y+2, fill=self.accent, outline='')
                continue
            flat = [v for point in points for v in point]
            self.create_polygon(points[0][0], h+1, *flat, points[-1][0], h+1,
                                fill=shade, outline='')
            self.create_line(*flat, fill=self.accent, width=2)
