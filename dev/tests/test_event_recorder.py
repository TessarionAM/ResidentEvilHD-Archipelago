"""Offline tests for the event recorder's helpers."""
import unittest

from hd_event_recorder import NoiseFilter, bit_changes, room_label


class RecorderTests(unittest.TestCase):
    def test_bit_changes_report_new_value(self):
        self.assertEqual(bit_changes(bytes([0b01]), bytes([0b10]), -0x10), [(-0x10, 0, 0), (-0x10, 1, 1)])

    def test_noise_filter_mutes_flickering_bits_only(self):
        f = NoiseFilter(flips=4, window=3.0)
        timer = (-0x3F0, 0, 1)
        kill = (+0x120, 5, 1)
        kept_all = []
        for i in range(6):
            kept, _ = f.keep([timer], 100 + i * 0.1)
            kept_all += kept
        self.assertEqual(len(kept_all), 3)                 # 3 shown, then muted
        self.assertIn((-0x3F0, 0), f.muted)
        kept, _ = f.keep([kill], 101)
        self.assertEqual(kept, [kill])                     # a one-off event still shows

    def test_room_labels(self):
        self.assertEqual(room_label(0x106), "Mansion - Main Hall")
        self.assertEqual(room_label(0x104), "unlisted room 0x104")
        self.assertEqual(room_label(None), "(loading)")



class HotkeyTests(unittest.TestCase):
    def test_label_once_per_press(self):
        from hd_event_recorder import Hotkeys
        k = Hotkeys()
        self.assertEqual(k.poll({0x2D: True}), ["enemy killed"])     # Insert pressed
        self.assertEqual(k.poll({0x2D: True}), [])                   # still held: no repeat
        self.assertEqual(k.poll({0x2D: False}), [])
        self.assertEqual(k.poll({0x24: True}), ["typewriter used"])  # Home


if __name__ == "__main__":
    unittest.main()
