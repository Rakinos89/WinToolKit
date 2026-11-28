import unittest
from modules.hardware_graph import graph_segments


class HardwareGraphTests(unittest.TestCase):
    def test_scale(self):
        self.assertEqual(graph_segments([(59, 0, 50, 100), (60, 100, 50, 0)], 1, 60, 60, 100), [[(59, 100), (60, 0)]])

    def test_metric(self):
        self.assertEqual(graph_segments([(60, 0, 50, 100)], 2, 60, 60, 100), [[(60, 50)]])

    def test_missing(self):
        self.assertEqual(len(graph_segments([(58, 0, None, None), (59, None, None, None), (60, 20, None, None)], 1, 60, 60, 100)), 2)

    def test_gap(self):
        self.assertEqual(len(graph_segments([(50, 10, None, None), (60, 20, None, None)], 1, 60, 60, 100)), 2)

    def test_outside_window(self):
        self.assertEqual(graph_segments([(-1, 10, None, None), (61, 20, None, None)], 1, 60, 60, 100), [])

    def test_invalid_values(self):
        self.assertEqual(graph_segments([(60, v, None, None) for v in (True, -1, 101, float('nan'))], 1, 60, 60, 100), [])

    def test_empty(self):
        self.assertEqual(graph_segments([], 1, 60, 60, 100), [])

    def test_invalid_metric(self):
        with self.assertRaises(ValueError):
            graph_segments([], 0, 60, 60, 100)
