import unittest
from modules.hardware_history import HardwareHistory


class HardwareHistoryTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.history = HardwareHistory(clock=lambda: self.now)

    def test_empty_history(self):
        self.assertEqual(self.history.snapshot(), ())

    def test_sample(self):
        self.history.append(25, 50, 75)
        self.assertEqual(self.history.snapshot(), ((100.0, 25.0, 50.0, 75.0),))

    def test_missing_and_zero(self):
        self.history.append(None, 0, 100)
        self.assertEqual(self.history.snapshot()[0][1:], (None, 0.0, 100.0))

    def test_invalid_percentages(self):
        for value in (True, -1, 101, float('nan'), float('inf'), '50'):
            self.history.append(value, value, value)
            self.assertEqual(self.history.snapshot()[-1][1:], (None, None, None))

    def test_bounded_history(self):
        for i in range(65):
            self.history.append(i, 50, 75)
        self.assertEqual(len(self.history.snapshot()), 60)
        self.assertEqual(self.history.snapshot()[0][1], 5)

    def test_expiration(self):
        self.history.append(10, 20, 30)
        self.now += 30
        self.history.append(20, 30, 40)
        self.now += 30
        self.assertEqual(len(self.history.snapshot()), 1)
        self.now += 30
        self.assertEqual(self.history.snapshot(), ())

    def test_clear(self):
        self.history.append(10, 20, 30)
        self.history.clear()
        self.assertEqual(self.history.snapshot(), ())

    def test_invalid_configuration(self):
        for count in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                HardwareHistory(max_samples=count)
        for seconds in (0, -1, float('inf'), float('nan')):
            with self.assertRaises(ValueError):
                HardwareHistory(window_seconds=seconds)


if __name__ == '__main__':
    unittest.main()
