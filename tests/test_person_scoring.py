import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import server


class PersonScoringTests(unittest.TestCase):
    def test_person_box_including_face_counts_but_huge_box_does_not(self):
        stage = server.STAGES[0]
        self.assertTrue(server.score_box([0.15, 0.46, 0.22, 0.66], stage)['correct'])
        self.assertFalse(server.score_box([0, 0, 1, 1], stage)['correct'])
        self.assertFalse(server.score_box(None, stage)['correct'])

    def test_face_center_and_unrelated_box(self):
        stage = server.STAGES[0]
        self.assertTrue(server.score_box([0.17, 0.47, 0.19, 0.51], stage)['correct'])
        self.assertFalse(server.score_box([0.5, 0.5, 0.52, 0.53], stage)['correct'])
