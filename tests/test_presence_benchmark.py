import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import presence_benchmark as presence


class PresenceTests(unittest.TestCase):
    def test_both_models_ask_binary_question_directly(self):
        scene = ROOT / 'data' / 'stages_v3' / 'stage1.png'
        for model in ('Jev', 'Clef'):
            captured = {}

            def open_request(request, timeout):
                captured['body'] = json.loads(request.data)
                answer = {'model': 'jev-1.14.0' if model == 'Jev' else 'clef',
                          'answers': {'target': {'choice': 'absent', 'confidence': 0.75}}}
                return io.BytesIO(json.dumps(answer if model == 'Jev' else {'success': True, 'result': answer}).encode())

            with self.subTest(model=model), patch.object(presence, 'read_key', return_value='test'), \
                 patch.object(presence, 'read_setting', side_effect=lambda name: 'a' * 32), \
                 patch.object(presence.urllib.request, 'urlopen', side_effect=open_request):
                result = presence.query(model, scene)
                self.assertEqual((result['choice'], result['confidence']), ('absent', 0.75))
                question = captured['body']['questions']['target']
                self.assertEqual(question['type'], 'choice')
                self.assertEqual(set(question['criteria']), {'present', 'absent'})
                self.assertIn(presence.PROMPT, question['instructions'])
                self.assertEqual(len(captured['body']['assets'] if model == 'Jev' else captured['body']['images']), 2)


if __name__ == '__main__':
    unittest.main()
