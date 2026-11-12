"""Tests des cas limites du lecteur, sans fenêtre ni vidéos externes."""

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

import numpy as np

import main


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        # 16 x 8 de luma, chroma 8 x 4 côte à côte.
        pixels = np.full((12, 16), 128, np.uint8)
        self.path = self.folder / "0.pgm"
        self.path.write_bytes(b"P5\n16 12\n255\n" + pixels.tobytes())
        self.seq = dict(width="16", height="8", progressive_sequence="0")
        self.flag = dict(n="0", type="I", progressive_frame="0",
                         top_field_first="1", repeat_first_field="0")
        self.args = Namespace(fps=None, deint="bob", threshold=10, block=3,
                              force_progressive=False, force_interlaced=False,
                              tff=False, bff=False)

    def render(self, flags=None):
        flags = flags or [self.flag]
        return list(main.images(self.args, [self.path] * len(flags), self.seq, flags))

    def test_cadence_priority_and_default(self):
        self.assertEqual(main.frame_period(None, {}), 1 / 25)
        self.assertEqual(main.frame_period(None, {"frame_period": "0"}), 1 / 25)
        self.assertAlmostEqual(main.frame_period(None, {"frame_period": "900900"}), 1001 / 30000)
        self.assertEqual(main.frame_period(10, {"frame_period": "900900"}), 0.1)
        for value in [0, -1, float("nan"), float("inf")]:
            with self.assertRaises(ValueError):
                main.frame_period(value, {})

    def test_bob_and_repeated_field_timing(self):
        y = np.broadcast_to(np.arange(8, dtype=np.float32)[:, None] * 16 + 16, (8, 16))
        u = np.full((4, 8), 128, np.float32)
        np.testing.assert_array_equal(main.to_rgb(y, u, u, 0)[:, 0, 0],
                                      [0, 18, 37, 55, 74, 93, 111, 111])
        np.testing.assert_array_equal(main.to_rgb(y, u, u, 1)[:, 0, 0],
                                      [18, 18, 37, 55, 74, 93, 111, 130])
        outputs = self.render()
        self.assertEqual(len(outputs), 2)
        self.assertAlmostEqual(sum(duration for _, duration, _ in outputs), 1 / 25)
        self.assertTrue(outputs[0][2].endswith("field T"))
        self.flag.update(top_field_first="0", repeat_first_field="1", nb_fields="3")
        outputs = self.render()
        self.assertEqual([title[-1] for _, _, title in outputs], ["B", "T", "B"])
        self.assertAlmostEqual(sum(duration for _, duration, _ in outputs), 1.5 / 25)

    def test_progressive_sequence_repeated_frame_duration(self):
        self.seq["progressive_sequence"] = "1"
        self.flag["nb_fields"] = "6"
        outputs = self.render()
        self.assertEqual(len(outputs), 1)
        self.assertAlmostEqual(outputs[0][1], 3 / 25)

    def test_partial_motion_blocks_include_last_pixel(self):
        a = np.zeros((35, 51), np.float32)
        b = a.copy()
        b[-1, -1] = 255
        mask = main.motion(a, b, 16, 1)
        self.assertEqual(mask.shape, (70, 51))
        self.assertTrue(mask[-1, -1])
        self.assertFalse(mask[0, 0])
        self.assertFalse(main.motion(a, a, 100, 1).any())

    def test_adaptive_handles_polarity_changes_and_repeat(self):
        self.args.deint = "adaptive"
        flags = [dict(self.flag, n=str(i), top_field_first=str(i % 2),
                      repeat_first_field="1", nb_fields="3") for i in range(5)]
        outputs = self.render(flags)
        self.assertEqual(len(outputs), 15)
        for rgb, _, _ in outputs:
            self.assertEqual(rgb.shape, (8, 16, 3))
            # Une image constante reste constante même aux bords des blocs.
            np.testing.assert_array_equal(rgb, np.broadcast_to(rgb[0, 0], rgb.shape))

    def test_weave_keeps_fields_separate_for_chroma(self):
        np.testing.assert_array_equal(
            main.horizontal_chroma(np.array([[0, 100, 200]], np.float32)),
            [[0, 50, 100, 150, 200, 200]])
        y = np.full((8, 16), 128, np.float32)
        u = np.full((4, 8), 128, np.float32)
        v = u.copy()
        u[0::2] = 32
        u[1::2] = 224
        rgb = main.to_rgb(y, u, v, interlaced=True)
        self.assertLess(rgb[0, 0, 2], rgb[1, 0, 2])
        np.testing.assert_array_equal(rgb[0::2], main.to_rgb(y, u, v, 0)[0::2])

    def test_flags_match_file_numbers_and_keep_sequence_metadata(self):
        (self.folder / "flags.log").write_text(
            "\n# exemple\nSEQ width=16 height=8\n"
            "FRAME 9 type=P\nFRAME 0 type=I\n"
            "SEQ width=32 height=16 frame_period=900900\nFRAME 10 type=B\n")
        files, seq, flags = main.load_inputs(self.folder)
        self.assertEqual(files, [self.path])
        self.assertEqual(flags[0]["n"], "0")
        self.assertEqual(flags[0]["sequence"]["width"], "16")
        self.assertEqual(seq["width"], "16")
        self.path.rename(self.folder / "1.pgm")
        with self.assertRaisesRegex(ValueError, "Flags absents"):
            main.load_inputs(self.folder)


if __name__ == "__main__":
    unittest.main()
