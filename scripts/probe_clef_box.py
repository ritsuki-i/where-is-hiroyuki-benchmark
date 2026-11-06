"""Probe whether Workers AI Clef accepts Jev's box question format."""
import json
import re
import urllib.error
import urllib.request
from server import ROOT, REFERENCE, STAGES, asset, read_setting

token = read_setting('CLOUDFLARE_API_TOKEN')
account = read_setting('CLOUDFLARE_ACCOUNT_ID')
if not token or not re.fullmatch(r'[0-9a-fA-F]{32}', account):
    raise SystemExit('Cloudflare credentials missing or invalid')
body = {'model':'clef',
        'images':['data:image/jpeg;base64,'+asset(REFERENCE)['data_base64'],
                  'data:image/jpeg;base64,'+asset(ROOT/'data/stages_v3'/STAGES[0]['image'])['data_base64']],
        'state':'The first image is reference; the second image is scene.',
        'questions':{'target':{'type':'box','instructions':'Locate in `scene` the person whose face matches the character in `reference`. His clothes and pose may differ; return the visible person, not the reference image.'}}}
request = urllib.request.Request(f'https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/cloudflare/clef',
    data=json.dumps(body).encode(), headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
try:
    with urllib.request.urlopen(request,timeout=90) as response:
        payload=json.load(response)
        print('HTTP',response.status,'success',payload.get('success'),'result keys',list(payload.get('result',{})))
except urllib.error.HTTPError as exc:
    payload=json.load(exc)
    errors=payload.get('errors',[])
    print('HTTP',exc.code,'error codes',[e.get('code') for e in errors if isinstance(e,dict)])
    print('error descriptions',[str(e.get('message',''))[:400] for e in errors if isinstance(e,dict)])
body['questions']['target'] = {'type':'choice','instructions':'Is the reference a person?', 'criteria':{'yes':'yes','no':'no'}}
request = urllib.request.Request(f'https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/cloudflare/clef',
    data=json.dumps(body).encode(), headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
try:
    with urllib.request.urlopen(request,timeout=90) as response:
        payload=json.load(response)
        print('control choice HTTP',response.status,'success',payload.get('success'))
except urllib.error.HTTPError as exc:
    print('control choice HTTP',exc.code)
