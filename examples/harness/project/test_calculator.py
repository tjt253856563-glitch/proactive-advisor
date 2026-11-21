import unittest

from calculator import add, label


class CalculatorTest(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(3, 1), 4)

    def test_label(self):
        self.assertEqual(label(), "old")
