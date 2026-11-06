"""Check that Clef chooses coordinates from images without a detector."""
import base64
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import server


class ClefDirectTests(unittest.TestCase):
    def run_with_choices(self,choices):
        captured={}
        class Response:
            def __enter__(self):
                answers={name:{'choice':choice,'confidence':0.5} for name,choice in choices.items()}
                return io.BytesIO(json.dumps({'success':True,'result':{'model':'clef','answers':answers}}).encode())
            def __exit__(self,*args): pass
        def urlopen(request,timeout):
            captured['body']=json.loads(request.data)
            return Response()
        settings=lambda name: 'a'*32 if name=='CLOUDFLARE_ACCOUNT_ID' else 'test-token'
        with patch.object(server,'read_setting',side_effect=settings),patch.object(server.urllib.request,'urlopen',side_effect=urlopen) as request:
            result=server.run_clef(0)
            self.assertEqual(request.call_count,1)
        return result,captured['body']

    def test_direct_images_and_discrete_coordinates(self):
        result,body=self.run_with_choices({'left':'p010','top':'p020','right':'p030','bottom':'p040'})
        self.assertEqual(result['box'],[0.1,0.2,0.3,0.4])
        self.assertEqual(set(body['questions']),{'left','top','right','bottom'})
        self.assertTrue(all(len(q['criteria'])==101 for q in body['questions'].values()))
        self.assertTrue(all(server.PROTOCOL['prompt'] in q['instructions'] for q in body['questions'].values()))
        self.assertEqual(base64.b64decode(body['images'][0].split(',',1)[1]),base64.b64decode(server.asset(server.REFERENCE)['data_base64']))

    def test_invalid_box_is_not_corrected(self):
        result,_=self.run_with_choices({'left':'p014','top':'p017','right':'p038','bottom':'p017'})
        self.assertIsNone(result['box'])
        self.assertFalse(result['correct'])
        self.assertTrue(result['invalid_coordinates'])
        self.assertEqual(result['coordinate_choices']['bottom'],'p017')


if __name__=='__main__':
    unittest.main()
