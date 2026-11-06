"""Checks for truthful race persistence and configuration drift."""
import copy
import http.client
import json
import sys
import tempfile
import unittest
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import server
import race_records


class RaceRecordTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.root=Path(self.directory.name)
        (self.root/'data/stages_v3').mkdir(parents=True)
        (self.root/'README.md').write_text('before\n'+race_records.START+'\nold\n'+race_records.END+'\nafter\n',encoding='utf-8')
        for stage in server.STAGES:
            Image.new('RGB',(80,60),'white').save(self.root/'data/stages_v3'/stage['image'])
        rows=[]
        for i,stage in enumerate(server.STAGES):
            x1,y1,x2,y2=stage['face_bbox_xyxy_approx']
            width,height=stage['width'],stage['height']
            rows.append({'stage':i+1,'box':[x1/width,y1/height,x2/width,y2/height],
                         'correct':True,'model':'test','stage_wall_seconds':0.5})
        self.payload={'run_id':'a'*32,'sha256':{'file':'expected'},'models':[
            {'name':'Jev','status':'completed','elapsed_text':'3.28','stages':copy.deepcopy(rows)},
            {'name':'Clef','status':'skipped','elapsed_text':None,'stages':[]},
            {'name':'Opus 5.5','status':'completed','elapsed_text':'43.20','stages':copy.deepcopy(rows)},
            {'name':'YuNet + SFace','status':'completed','elapsed_text':'11.10','stages':copy.deepcopy(rows)}]}
        for model,version in ((self.payload['models'][0],'jev-1.14.0'),
                              (self.payload['models'][2],'claude-opus-5-5'),
                              (self.payload['models'][3],'YuNet + SFace')):
            for row in model['stages']:
                row['model']=version
                if model['name'] in ('Jev','Opus 5.5'):
                    row['prompt']=server.PROTOCOL['prompt']+' '+(server.PROTOCOL['models']['Jev']['prompt_suffix'] if model['name']=='Jev' else server.PROTOCOL['models']['Opus']['prompt_suffix'])
                    row['prepared_sha256']={'reference':'b'*64,'scene':'c'*64}
        self.snapshot={'sha256':{'file':'expected'},'protocol':server.PROTOCOL}

    def tearDown(self):
        self.directory.cleanup()

    def save(self,payload):
        with patch.object(race_records,'ROOT',self.root),patch.object(race_records,'snapshot',return_value=self.snapshot):
            return race_records.save(payload,self.root/'reference.png',server.STAGES,server.score_box)

    def test_displayed_values_are_saved_and_rendered_from_same_run(self):
        result=self.save(self.payload)
        record=json.loads((self.root/result['result_file']).read_text(encoding='utf-8'))
        readme=(self.root/'README.md').read_text(encoding='utf-8')
        self.assertIn('| Jev | 5 / 5 | 3.28秒 | 完了 |',readme)
        self.assertIn('| Clef | — | — | 未実行 |',readme)
        self.assertEqual(record['models'][2]['elapsed_text'],'43.20')
        for i in range(1,6):
            self.assertTrue((self.root/'docs/runs'/self.payload['run_id']/f'stage{i}.jpg').exists())

    def test_rejects_inconsistent_score_and_fabricated_clef(self):
        bad=copy.deepcopy(self.payload)
        bad['models'][0]['stages'][0]['correct']=False
        with self.assertRaises(ValueError): self.save(bad)
        bad=copy.deepcopy(self.payload)
        bad['models'][1]={'name':'Clef','status':'completed','elapsed_text':'1.00','stages':bad['models'][0]['stages']}
        with self.assertRaises(ValueError): self.save(bad)
        bad=copy.deepcopy(self.payload)
        bad['models'][2]['stages'][0]['model']='different-model'
        with self.assertRaises(ValueError): self.save(bad)
        bad=copy.deepcopy(self.payload)
        bad['models'][2]['stages'][0]['prepared_sha256']['scene']='d'*64
        with self.assertRaises(ValueError): self.save(bad)

    def test_clef_coordinate_choices_are_saved_without_repair(self):
        payload=copy.deepcopy(self.payload)
        fields=server.PROTOCOL['models']['Clef']['coordinate_fields']
        questions={name:server.PROTOCOL['models']['Clef']['question_template'].format(task=server.PROTOCOL['prompt'],description=description) for name,description in fields.items()}
        rows=[]
        for i,stage in enumerate(server.STAGES):
            choices={'left':'p010','top':'p020','right':'p030','bottom':'p040'}
            box=[int(choices[name][1:])*0.01 for name in ('left','top','right','bottom')]
            rows.append({'stage':i+1,'box':box,'correct':server.score_box(box,stage)['correct'],
                         'model':'@cf/cloudflare/clef','stage_wall_seconds':0.5,
                         'prompt':server.PROTOCOL['prompt'],'prepared_sha256':{'reference':'b'*64,'scene':'c'*64},
                         'coordinate_choices':choices,'coordinate_questions':questions,'invalid_coordinates':False})
        rows[0].update(box=None,correct=False,invalid_coordinates=True,
                       coordinate_choices={'left':'p010','top':'p020','right':'p030','bottom':'p020'})
        payload['models'][1]={'name':'Clef','status':'completed','elapsed_text':'12.82','stages':rows}
        result=self.save(payload)
        record=json.loads((self.root/result['result_file']).read_text(encoding='utf-8'))
        self.assertIsNone(record['models'][1]['stages'][0]['box'])
        self.assertTrue(record['models'][1]['stages'][0]['invalid_coordinates'])
        self.assertEqual(record['models'][1]['stages'][0]['coordinate_choices']['bottom'],'p020')
        self.assertIn('12.82秒',(self.root/'README.md').read_text(encoding='utf-8'))

    def test_rejects_changed_configuration(self):
        bad=copy.deepcopy(self.payload)
        bad['sha256']['file']='different'
        with self.assertRaises(ValueError): self.save(bad)
        self.assertFalse((self.root/'results').exists())

    def test_interrupted_model_keeps_the_displayed_denominator(self):
        bad=copy.deepcopy(self.payload)
        rows=bad['models'][0]['stages'][:2]
        rows.append({'stage':3,'error':'connection failed','stage_wall_seconds':0.5})
        bad['models'][0].update(status='error',elapsed_text='3.28',stages=rows)
        self.save(bad)
        readme=(self.root/'README.md').read_text(encoding='utf-8')
        self.assertIn('| Jev | 2 / 5（未完了） | 3.28秒 | エラーで中断 |',readme)

    def test_http_save_matches_display_and_rejects_foreign_origin(self):
        with patch.object(race_records,'ROOT',self.root),patch.object(race_records,'snapshot',return_value=self.snapshot),patch.object(server,'run_snapshot',return_value=self.snapshot):
            httpd=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            worker=threading.Thread(target=httpd.serve_forever,daemon=True)
            worker.start()
            try:
                body=json.dumps(self.payload)
                conn=http.client.HTTPConnection('127.0.0.1',httpd.server_port,timeout=10)
                conn.request('POST','/api/runs',body=body,headers={'Host':'127.0.0.1:8765','Origin':'https://invalid.example','Content-Type':'application/json'})
                response=conn.getresponse()
                self.assertEqual(response.status,403)
                response.read()
                conn.request('POST','/api/runs',body=body,headers={'Host':'127.0.0.1:8765','Origin':'http://127.0.0.1:8765','Content-Type':'application/json'})
                response=conn.getresponse()
                self.assertEqual(response.status,200)
                result=json.loads(response.read())
                self.assertEqual(result['run_id'],self.payload['run_id'])
                self.assertIn('3.28秒',(self.root/'README.md').read_text(encoding='utf-8'))
                conn.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
                worker.join(timeout=5)


if __name__=='__main__':
    unittest.main()
