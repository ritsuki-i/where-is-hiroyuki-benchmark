"""Local race viewer and server-side Jev proxy. Never exposes credentials."""
import base64
import io
import json
import math
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
STAGES = json.loads((ROOT/'data/stages_v3/annotations_draft.json').read_text(encoding='utf-8'))['stages']
REFERENCE = next((ROOT/'hiroyuki').glob('*.png'))
MODEL = 'jev-1.14.0'

def read_key():
    if os.environ.get('TYPESAFE_API_KEY'):
        return os.environ['TYPESAFE_API_KEY'].strip()
    path = ROOT/'.env.local'
    if not path.exists(): return ''
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if line.startswith('TYPESAFE_API_KEY='):
            return line.split('=',1)[1].strip().strip('"\'')
    return ''

def asset(path):
    im = Image.open(path).convert('RGB')
    return image_asset(im)

def image_asset(im):
    im.thumbnail((1568,1568), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    im.save(out, format='JPEG', quality=90)
    return {'type':'image','format':'jpg','data_base64':base64.b64encode(out.getvalue()).decode('ascii')}

def score_box(coords, stage):
    width, height = stage['width'], stage['height']
    gx1, gy1, gx2, gy2 = stage['face_bbox_xyxy_approx']
    target = [gx1/width, gy1/height, gx2/width, gy2/height]
    if coords is None:
        return {'target_box': target, 'correct': False}
    x1, y1, x2, y2 = coords
    ix = max(0.0, min(x2, target[2]) - max(x1, target[0]))
    iy = max(0.0, min(y2, target[3]) - max(y1, target[1]))
    intersection = ix * iy
    target_area = (target[2]-target[0]) * (target[3]-target[1])
    prediction_area = (x2-x1) * (y2-y1)
    coverage = intersection / target_area
    iou = intersection / (target_area + prediction_area - intersection)
    return {'target_box':target, 'coverage':coverage, 'iou':iou,
            'correct':target[0] <= (x1+x2)/2 <= target[2] and target[1] <= (y1+y2)/2 <= target[3]}

def run_jev(index):
    key=read_key()
    if not key: raise RuntimeError('TYPESAFE_API_KEY が設定されていません')
    stage=STAGES[index]
    scene_ref='scene-'+uuid.uuid4().hex
    target_ref='target-'+uuid.uuid4().hex
    body={'model':MODEL,'state':{'scene':scene_ref,'reference':target_ref},
          'assets':{scene_ref:asset(ROOT/'data/stages_v3'/stage['image']),target_ref:asset(REFERENCE)},
          'questions':{'target':{'type':'box','instructions':'Locate in `scene` the person whose face matches the character in `reference`. His clothes and pose may differ. Return a tight box around only the visible face in `scene`, not the body or reference image.'}}}
    req=urllib.request.Request('https://api.typesafe.ai/v1/systemone', data=json.dumps(body).encode(), method='POST', headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','TypeSafe-Danger-Zone-Images':'true'})
    start=time.perf_counter()
    try:
        with urllib.request.urlopen(req,timeout=90) as response: payload=json.load(response)
    except urllib.error.HTTPError as e:
        # Do not return raw upstream bodies; they can contain request details.
        raise RuntimeError(f'Jev API HTTP {e.code}') from e
    elapsed=time.perf_counter()-start
    answer=payload.get('answers',{}).get('target',{})
    box=answer.get('box',{})
    try:
        coords=[float(box[k]) for k in ('left','top','right','bottom')]
        if not all(math.isfinite(n) and 0<=n<=1 for n in coords) or coords[0]>=coords[2] or coords[1]>=coords[3]: raise ValueError()
    except (ValueError,TypeError,KeyError): raise RuntimeError('Jev の矩形応答を解釈できません')
    confidence=answer.get('confidence')
    if isinstance(confidence,bool) or not isinstance(confidence,(int,float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        confidence=None
    return {'box':coords,'confidence':confidence,**score_box(coords,stage),'seconds':elapsed,'model':payload.get('model',MODEL)}

def run_face(index):
    from face_search import search
    stage = STAGES[index]
    result = search(ROOT/'data/stages_v3'/stage['image'], REFERENCE)
    result.update(**score_box(result['box'], stage), model='YuNet + SFace')
    return result

def run_jev_candidates(index):
    from jev_candidates import make_candidates
    start = time.perf_counter()
    key = read_key()
    if not key:
        raise RuntimeError('TYPESAFE_API_KEY が設定されていません')
    stage = STAGES[index]
    sheet, boxes = make_candidates(ROOT/'data/stages_v3'/stage['image'])
    if not boxes:
        return {'box':None, 'confidence':None, 'candidates':0, **score_box(None, stage), 'seconds':time.perf_counter()-start, 'model':'YuNet + Jev'}
    sheet_ref = 'candidates-'+uuid.uuid4().hex
    target_ref = 'reference-'+uuid.uuid4().hex
    choices = {f'face_{i+1:03d}': f'The face labeled face_{i+1:03d} in the candidate sheet.' for i in range(len(boxes))}
    choices['none'] = 'None of the candidate faces matches the reference.'
    body = {'model':MODEL, 'state':{'reference':target_ref,'candidate_sheet':sheet_ref},
            'assets':{target_ref:asset(REFERENCE),sheet_ref:image_asset(sheet)},
            'questions':{'target':{'type':'choice', 'instructions':'Which labeled face in candidate_sheet matches the person in reference? Select its exact label, or none if no face matches.', 'criteria':choices}}}
    req = urllib.request.Request('https://api.typesafe.ai/v1/systemone', data=json.dumps(body).encode(), method='POST', headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','TypeSafe-Danger-Zone-Images':'true'})
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'Jev API HTTP {e.code}') from e
    answer = payload.get('answers', {}).get('target', {})
    choice = answer.get('choice')
    if choice not in choices:
        raise RuntimeError('Jevの候補選択を解釈できません')
    box = None if choice == 'none' else boxes[int(choice[5:])-1]
    confidence = answer.get('confidence')
    if isinstance(confidence, bool) or not isinstance(confidence, (int,float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        confidence = None
    return {'box':box,'confidence':confidence,'choice':choice,'candidates':len(boxes),**score_box(box,stage),'seconds':time.perf_counter()-start,'model':'YuNet + '+payload.get('model',MODEL)}

def run_claude(index, model_id):
    cli = shutil.which('claude.cmd') or shutil.which('claude')
    if not cli:
        raise RuntimeError('Claude Codeが見つかりません')
    env = os.environ.copy()
    for key in ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_USE_BEDROCK', 'CLAUDE_CODE_USE_VERTEX', 'CLAUDE_CODE_USE_FOUNDRY'):
        env.pop(key, None)
    try:
        auth = subprocess.run([cli, 'auth', 'status'], capture_output=True, text=True, encoding='utf-8', timeout=20, env=env, cwd=ROOT)
        status = json.loads(auth.stdout)
        if not status.get('loggedIn') or status.get('authMethod') != 'claude.ai' or not status.get('subscriptionType'):
            raise RuntimeError('Claudeのサブスク認証を確認できません')
        stage = STAGES[index]
        scene = (ROOT/'data/stages_v3'/stage['image']).resolve()
        prompt = (f'Read these two images using the Read tool: reference image "{REFERENCE.resolve()}" and scene image "{scene}". '
                  'Find the person in the scene whose face matches the reference; their clothes and pose may differ. '
                  'Give a tight bounding box around only the visible face of that person in the SCENE, not the body, as normalized 0 to 1 coordinates '
                  'in JSON only: {"box": [left, top, right, bottom]}. Do not use any other files or tools.')
        started = time.perf_counter()
        proc = subprocess.run([cli, '-p', prompt, '--model', model_id, '--safe-mode', '--restricted', '--strict-mcp-config', '--tools', 'Read', '--allowedTools', 'Read', '--permission-mode', 'dontAsk', '--output-format', 'json'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180, env=env, cwd=ROOT)
        elapsed = time.perf_counter()-started
        payload = json.loads(proc.stdout)
        if proc.returncode or payload.get('is_error'):
            raise RuntimeError('Claudeの実行に失敗しました。Claude Codeの認証または利用上限を確認してください')
        response = payload.get('result', '').strip()
        parsed = None
        for offset, char in enumerate(response):
            if char == '{':
                try:
                    candidate, _ = json.JSONDecoder().raw_decode(response[offset:])
                    if isinstance(candidate, dict) and 'box' in candidate:
                        parsed = candidate
                        break
                except json.JSONDecodeError:
                    continue
        if parsed is None:
            raise ValueError('missing box')
        coords = parsed['box']
        if not isinstance(coords, list) or len(coords) != 4 or any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) or not 0 <= n <= 1 for n in coords) or coords[0] >= coords[2] or coords[1] >= coords[3]:
            raise ValueError('invalid box')
        model = next(iter(payload.get('modelUsage', {})), model_id)
        return {'box': coords, 'confidence': None, **score_box(coords, stage), 'seconds': elapsed, 'model': model}
    except (json.JSONDecodeError, KeyError, ValueError):
        raise RuntimeError('Claudeの矩形応答または認証情報を解釈できません') from None
    except subprocess.TimeoutExpired:
        raise RuntimeError('Claudeがタイムアウトしました') from None

def run_sonnet(index):
    return run_claude(index, 'claude-sonnet-5-5')

def run_opus(index):
    return run_claude(index, 'opus')

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def respond(self,status,data,content='application/json; charset=utf-8'):
        self.send_response(status);self.send_header('Content-Type',content);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
    def do_GET(self):
        routes={'/':('viewer/race.html','text/html; charset=utf-8'),'/race.js':('viewer/race.js','text/javascript; charset=utf-8'),'/race.css':('viewer/race.css','text/css; charset=utf-8'),'/reference':(str(REFERENCE.relative_to(ROOT)),'image/png')}
        for i in range(1,6): routes[f'/stage/{i}']=(f'data/stages_v3/stage{i}.png','image/png')
        if self.path not in routes: return self.respond(404,b'Not found','text/plain')
        path,mime=routes[self.path]
        return self.respond(200,(ROOT/path).read_bytes(),mime)
    def do_POST(self):
        if self.path not in ('/api/jev','/api/face','/api/sonnet','/api/jev-candidates'): return self.respond(404,b'Not found','text/plain')
        # Prevent browser cross-origin and DNS-rebinding requests to this local proxy.
        if self.headers.get('Host') not in ('127.0.0.1:8765','localhost:8765') or self.headers.get('Origin') not in ('http://127.0.0.1:8765','http://localhost:8765'):
            return self.respond(403,b'{"error":"Forbidden"}')
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length>1024: raise ValueError('invalid request')
            body=json.loads(self.rfile.read(length))
            index=body.get('stage')
            if type(index) is not int or index not in range(1,6): raise ValueError('invalid stage')
            result={'/api/jev':run_jev,'/api/face':run_face,'/api/sonnet':run_sonnet,'/api/jev-candidates':run_jev_candidates}[self.path](index-1)
            self.respond(200,json.dumps(result).encode())
        except (ValueError,RuntimeError,urllib.error.URLError,TimeoutError,OSError) as e:
            message=str(e) if isinstance(e,(ValueError,RuntimeError)) else 'Jev API への接続に失敗しました'
            self.respond(502,json.dumps({'error':message},ensure_ascii=False).encode())

if __name__=='__main__':
    print('Open http://127.0.0.1:8765',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
