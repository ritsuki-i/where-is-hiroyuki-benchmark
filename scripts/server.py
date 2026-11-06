"""Local race viewer and server-side Jev proxy. Never exposes credentials."""
import base64
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
STAGES = json.loads((ROOT/'data/stages_v3/annotations_draft.json').read_text(encoding='utf-8'))['stages']
REFERENCE = next((ROOT/'hiroyuki').glob('*.png'))
PROTOCOL = json.loads((ROOT/'benchmark_protocol.json').read_text(encoding='utf-8'))
MODEL = PROTOCOL['models']['Jev']['version']
PORT = int(os.environ.get('RACE_PORT','8765'))
if not 1024 <= PORT <= 65535:
    raise ValueError('RACE_PORT must be between 1024 and 65535')
LOADED_HASHES = {str(path.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in (Path(__file__),ROOT/'benchmark_protocol.json',ROOT/'data/stages_v3/annotations_draft.json',
                              ROOT/'scripts/face_search.py',ROOT/'scripts/race_records.py')}

def run_snapshot():
    from race_records import snapshot
    result = snapshot(REFERENCE,STAGES)
    if any(result['sha256'].get(name) != value for name,value in LOADED_HASHES.items()):
        raise RuntimeError('サーバー起動後にコードや設定が変更されました。サーバーを再起動してください')
    return result

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

def read_setting(name):
    value = os.environ.get(name, '').strip()
    if value:
        return value
    path = ROOT/'.env.local'
    if not path.exists():
        return ''
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        key, separator, value = line.strip().partition('=')
        if separator and key == name:
            return value.strip().strip('"\'')
    return ''

def asset(path):
    im = Image.open(path).convert('RGB')
    return image_asset(im)

def image_asset(im):
    max_side=PROTOCOL['direct_image_preprocessing']['max_side']
    im.thumbnail((max_side,max_side), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    im.save(out, format='JPEG', quality=PROTOCOL['direct_image_preprocessing']['jpeg_quality'])
    return {'type':'image','format':'jpg','data_base64':base64.b64encode(out.getvalue()).decode('ascii')}

def score_box(coords, stage, target_kind='face'):
    width, height = stage['width'], stage['height']
    gx1, gy1, gx2, gy2 = stage['bbox_xyxy_approx' if target_kind == 'person' else 'face_bbox_xyxy_approx']
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
    correct = (coverage >= 0.5 and iou >= 0.1) if target_kind == 'person' else (target[0] <= (x1+x2)/2 <= target[2] and target[1] <= (y1+y2)/2 <= target[3])
    return {'target_box':target, 'coverage':coverage, 'iou':iou, 'correct':correct}

def run_jev(index):
    key=read_key()
    if not key: raise RuntimeError('TYPESAFE_API_KEY が設定されていません')
    stage=STAGES[index]
    scene_ref='scene-'+uuid.uuid4().hex
    target_ref='target-'+uuid.uuid4().hex
    body={'model':MODEL,'state':{'scene':scene_ref,'reference':target_ref},
          'assets':{scene_ref:asset(ROOT/'data/stages_v3'/stage['image']),target_ref:asset(REFERENCE)},
          'questions':{'target':{'type':'box','instructions':PROTOCOL['prompt']+' The scene is `scene` and the reference image is `reference`.'}}}
    req=urllib.request.Request('https://api.typesafe.ai/v1/systemone', data=json.dumps(body).encode(), method='POST', headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','TypeSafe-Danger-Zone-Images':'true'})
    start=time.perf_counter()
    try:
        with urllib.request.urlopen(req,timeout=PROTOCOL['models']['Jev']['max_request_seconds']) as response: payload=json.load(response)
    except urllib.error.HTTPError as e:
        # Do not return raw upstream bodies; they can contain request details.
        raise RuntimeError(f'Jev API HTTP {e.code}') from e
    elapsed=time.perf_counter()-start
    if payload.get('model') != MODEL:
        raise RuntimeError('Jevの応答モデルが指定したバージョンと一致しません')
    answer=payload.get('answers',{}).get('target',{})
    box=answer.get('box',{})
    try:
        coords=[float(box[k]) for k in ('left','top','right','bottom')]
        if not all(math.isfinite(n) and 0<=n<=1 for n in coords) or coords[0]>=coords[2] or coords[1]>=coords[3]: raise ValueError()
    except (ValueError,TypeError,KeyError): raise RuntimeError('Jev の矩形応答を解釈できません')
    confidence=answer.get('confidence')
    if isinstance(confidence,bool) or not isinstance(confidence,(int,float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        confidence=None
    prepared_hashes={name:hashlib.sha256(base64.b64decode(body['assets'][ref]['data_base64'])).hexdigest()
                     for name,ref in (('reference',target_ref),('scene',scene_ref))}
    return {'box':coords,'confidence':confidence,**score_box(coords,stage),'seconds':elapsed,'model':payload['model'],
            'prompt':body['questions']['target']['instructions'],'prepared_sha256':prepared_hashes}

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

def run_clef_candidates(index):
    """Select a YuNet face candidate using Cloudflare Workers AI Clef."""
    from jev_candidates import make_candidates
    start = time.perf_counter()
    token = read_setting('CLOUDFLARE_API_TOKEN')
    account = read_setting('CLOUDFLARE_ACCOUNT_ID')
    if not token or not account:
        raise RuntimeError('CLOUDFLARE_API_TOKEN または CLOUDFLARE_ACCOUNT_ID が設定されていません')
    if not re.fullmatch(r'[0-9a-fA-F]{32}', account):
        raise RuntimeError('CloudflareアカウントIDの形式が不正です')
    stage = STAGES[index]
    sheet, boxes = make_candidates(ROOT/'data/stages_v3'/stage['image'])
    if not boxes:
        return {'box':None,'confidence':None,'choice':'none','candidates':0,
                **score_box(None,stage),'seconds':time.perf_counter()-start,'model':'@cf/cloudflare/clef'}
    options = {f'face_{i+1:03d}':f'The face labeled face_{i+1:03d} in the candidate sheet.' for i in range(len(boxes))}
    options['none'] = 'None of the candidate faces matches the reference.'
    images = ['data:image/jpeg;base64,'+asset(REFERENCE)['data_base64'],
              'data:image/jpeg;base64,'+image_asset(sheet)['data_base64']]
    body = {'model':'clef', 'images':images,
            'state':'The first image is the reference character. The second image is a numbered candidate face sheet.',
            'questions':{'target':{'type':'choice',
                                   'instructions':'Which labeled face in the second image matches the person in the first image? Select the exact face label, or none if no face matches.',
                                   'criteria':options}}}
    url = f'https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/cloudflare/clef'
    req = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'), method='POST',
                                 headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=90) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'Cloudflare Clef API HTTP {exc.code}') from None
    if not isinstance(payload,dict) or not payload.get('success') or not isinstance(payload.get('result'),dict):
        raise RuntimeError('Cloudflare Clef APIがエラーを返しました')
    result = payload['result']
    answer = result.get('answers',{}).get('target',{})
    choice = answer.get('choice') if isinstance(answer,dict) else None
    if choice not in options:
        raise RuntimeError('Cloudflare Clefの候補選択を解釈できません')
    box = None if choice == 'none' else boxes[int(choice[5:])-1]
    confidence = answer.get('confidence')
    if isinstance(confidence,bool) or not isinstance(confidence,(int,float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        confidence = None
    return {'box':box,'confidence':confidence,'choice':choice,'candidates':len(boxes),
            **score_box(box,stage),'seconds':time.perf_counter()-start,'model':'@cf/cloudflare/clef',
            'usage':result.get('usage')}

def run_clef(index):
    """Use Clef alone to choose four discrete box coordinates in one request."""
    token = read_setting('CLOUDFLARE_API_TOKEN')
    account = read_setting('CLOUDFLARE_ACCOUNT_ID')
    if not token or not account:
        raise RuntimeError('CLOUDFLARE_API_TOKEN または CLOUDFLARE_ACCOUNT_ID が設定されていません')
    if not re.fullmatch(r'[0-9a-fA-F]{32}',account):
        raise RuntimeError('CloudflareアカウントIDの形式が不正です')
    stage = STAGES[index]
    start = time.perf_counter()
    ref = asset(REFERENCE)
    scene = asset(ROOT/'data/stages_v3'/stage['image'])
    options = {f'p{i:03d}':f'{i} percent' for i in range(PROTOCOL['models']['Clef']['coordinate_options'])}
    fields = PROTOCOL['models']['Clef']['coordinate_fields']
    questions = {name:{'type':'choice',
                       'instructions':PROTOCOL['models']['Clef']['question_template'].format(task=PROTOCOL['prompt'],description=description),
                       'criteria':options} for name,description in fields.items()}
    body = {'model':'clef',
            'images':['data:image/jpeg;base64,'+ref['data_base64'],'data:image/jpeg;base64,'+scene['data_base64']],
            'state':PROTOCOL['models']['Clef']['state'],
            'questions':questions}
    url=f'https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/cloudflare/clef'
    request=urllib.request.Request(url,data=json.dumps(body).encode('utf-8'),method='POST',
                                   headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=PROTOCOL['models']['Clef']['max_request_seconds']) as response:
            payload=json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'Cloudflare Clef API HTTP {exc.code}') from None
    if not isinstance(payload,dict) or not payload.get('success') or not isinstance(payload.get('result'),dict):
        raise RuntimeError('Cloudflare Clef APIがエラーを返しました')
    result=payload['result']
    if result.get('model') not in ('clef','@cf/cloudflare/clef'):
        raise RuntimeError('Clefの応答モデルを確認できません')
    answers=result.get('answers',{})
    selected={}
    axis_confidence={}
    for name in fields:
        answer=answers.get(name,{})
        choice=answer.get('choice') if isinstance(answer,dict) else None
        if choice not in options:
            raise RuntimeError('Clefの座標応答を解釈できません')
        selected[name]=choice
        value=answer.get('confidence')
        axis_confidence[name]=value if not isinstance(value,bool) and isinstance(value,(int,float)) and math.isfinite(value) and 0<=value<=1 else None
    coords=[int(selected[name][1:])*PROTOCOL['models']['Clef']['coordinate_step'] for name in fields]
    valid=coords[0]<coords[2] and coords[1]<coords[3]
    box=coords if valid else None
    prepared={'reference':hashlib.sha256(base64.b64decode(ref['data_base64'])).hexdigest(),
              'scene':hashlib.sha256(base64.b64decode(scene['data_base64'])).hexdigest()}
    return {'box':box,'confidence':None,**score_box(box,stage),'model':'@cf/cloudflare/clef',
            'seconds':time.perf_counter()-start,'prompt':PROTOCOL['prompt'],'prepared_sha256':prepared,
            'coordinate_questions':{name:question['instructions'] for name,question in questions.items()},
            'coordinate_choices':selected,'axis_confidence':axis_confidence,
            'invalid_coordinates':not valid,'usage':result.get('usage')}

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
        scene = ROOT/'data/stages_v3'/stage['image']
        started = time.perf_counter()
        # Claude's restricted workspace contains only the two input images;
        # annotation files and other project material cannot be read.
        with tempfile.TemporaryDirectory(prefix='face-race-') as workdir:
            reference_copy = Path(workdir)/'reference.jpg'
            scene_copy = Path(workdir)/'scene.jpg'
            # Match the exact JPEG conversion used for Jev, not a second resize.
            reference_copy.write_bytes(base64.b64decode(asset(REFERENCE)['data_base64']))
            scene_copy.write_bytes(base64.b64decode(asset(scene)['data_base64']))
            prompt = (f'Read these two images using the Read tool: reference image "{reference_copy}" and scene image "{scene_copy}". '
                      + PROTOCOL['prompt'] + ' Use normalized 0 to 1 coordinates in JSON only: '
                      '{"box": [left, top, right, bottom]}. Do not use any other files or tools.')
            prepared_hashes={'reference':hashlib.sha256(reference_copy.read_bytes()).hexdigest(),
                             'scene':hashlib.sha256(scene_copy.read_bytes()).hexdigest()}
            proc = subprocess.run([cli, '-p', prompt, '--model', model_id, '--safe-mode', '--restricted', '--strict-mcp-config', '--tools', 'Read', '--allowedTools', 'Read', '--permission-mode', 'dontAsk', '--output-format', 'json', '--system-prompt', PROTOCOL['models']['Opus']['system_prompt']], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=PROTOCOL['models']['Opus']['max_request_seconds'], env=env, cwd=workdir)
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
        model_usage = payload.get('modelUsage')
        if not isinstance(model_usage,dict) or set(model_usage) != {model_id}:
            raise RuntimeError('Claudeの応答モデルが指定したバージョンと一致しません')
        model = model_id
        return {'box': coords, 'confidence': None, **score_box(coords, stage), 'seconds': elapsed, 'model': model,
                'prompt':prompt,'prepared_sha256':prepared_hashes}
    except (json.JSONDecodeError, KeyError, ValueError):
        raise RuntimeError('Claudeの矩形応答または認証情報を解釈できません') from None
    except subprocess.TimeoutExpired:
        raise RuntimeError('Claudeがタイムアウトしました') from None

def run_sonnet(index):
    return run_claude(index, 'claude-sonnet-5-5')

def run_opus(index):
    return run_claude(index, PROTOCOL['models']['Opus']['version'])

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def respond(self,status,data,content='application/json; charset=utf-8'):
        self.send_response(status);self.send_header('Content-Type',content);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
    def do_GET(self):
        if self.path == '/api/run-config':
            try:
                return self.respond(200,json.dumps(run_snapshot(),ensure_ascii=False).encode('utf-8'))
            except (RuntimeError,OSError) as e:
                return self.respond(500,json.dumps({'error':str(e)},ensure_ascii=False).encode('utf-8'))
        routes={'/':('viewer/race.html','text/html; charset=utf-8'),'/race.js':('viewer/race.js','text/javascript; charset=utf-8'),'/race.css':('viewer/race.css','text/css; charset=utf-8'),'/protocol.json':('benchmark_protocol.json','application/json; charset=utf-8'),'/reference':(str(REFERENCE.relative_to(ROOT)),'image/png')}
        for i in range(1,6): routes[f'/stage/{i}']=(f'data/stages_v3/stage{i}.png','image/png')
        if self.path not in routes: return self.respond(404,b'Not found','text/plain')
        path,mime=routes[self.path]
        data=(ROOT/path).read_bytes()
        if self.path == '/':
            js_hash=hashlib.sha256((ROOT/'viewer/race.js').read_bytes()).hexdigest().encode('ascii')
            css_hash=hashlib.sha256((ROOT/'viewer/race.css').read_bytes()).hexdigest().encode('ascii')
            html_hash=hashlib.sha256(data).hexdigest().encode('ascii')
            data=data.replace(b'__RACE_JS_SHA256__',js_hash).replace(b'__RACE_CSS_SHA256__',css_hash).replace(b'__RACE_HTML_SHA256__',html_hash)
        return self.respond(200,data,mime)
    def do_POST(self):
        if self.path not in ('/api/jev','/api/face','/api/sonnet','/api/opus','/api/jev-candidates','/api/clef','/api/clef-candidates','/api/runs'): return self.respond(404,b'Not found','text/plain')
        # Prevent browser cross-origin and DNS-rebinding requests to this local proxy.
        if self.headers.get('Host') not in (f'127.0.0.1:{PORT}',f'localhost:{PORT}') or self.headers.get('Origin') not in (f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}'):
            return self.respond(403,b'{"error":"Forbidden"}')
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<1 or length>(65536 if self.path == '/api/runs' else 1024): raise ValueError('invalid request')
            body=json.loads(self.rfile.read(length))
            if self.path == '/api/runs':
                from race_records import save
                run_snapshot()
                result=save(body,REFERENCE,STAGES,score_box)
                return self.respond(200,json.dumps(result,ensure_ascii=False).encode('utf-8'))
            index=body.get('stage')
            if type(index) is not int or index not in range(1,6): raise ValueError('invalid stage')
            result={'/api/jev':run_jev,'/api/face':run_face,'/api/sonnet':run_sonnet,'/api/opus':run_opus,'/api/jev-candidates':run_jev_candidates,'/api/clef':run_clef,'/api/clef-candidates':run_clef_candidates}[self.path](index-1)
            self.respond(200,json.dumps(result).encode())
        except (ValueError,RuntimeError,urllib.error.URLError,TimeoutError,OSError) as e:
            message=str(e) if isinstance(e,(ValueError,RuntimeError)) else 'Jev API への接続に失敗しました'
            self.respond(502,json.dumps({'error':message},ensure_ascii=False).encode())

class RaceServer(ThreadingHTTPServer):
    # On Windows, SO_REUSEADDR can make an old and a new server share one port.
    allow_reuse_address = False

if __name__=='__main__':
    httpd=RaceServer(('127.0.0.1',PORT),Handler)
    print(f'Open http://127.0.0.1:{PORT}',flush=True)
    httpd.serve_forever()
