"""Standalone yes/no presence pilot; does not modify saved video races."""
import base64
import datetime
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
import uuid

from server import ROOT, REFERENCE, STAGES, asset, read_key, read_setting

PROMPT = ('Does the scene contain the person whose face matches the reference character? '
          'Their clothes and pose may differ. Answer present or absent.')
CRITERIA = {'present': 'The reference person is present in the scene.',
            'absent': 'The reference person is absent from the scene.'}
STATE = 'The first image is the reference character. The second image is the scene.'


def query(model, scene_path):
    reference = asset(REFERENCE)
    scene = asset(scene_path)
    if model == 'Jev':
        key = read_key()
        if not key:
            raise RuntimeError('TYPESAFE_API_KEY is missing')
        refs = ['reference-' + uuid.uuid4().hex, 'scene-' + uuid.uuid4().hex]
        prompt = PROMPT + ' The scene is `scene` and the reference image is `reference`.'
        body = {'model': 'jev-1.14.0', 'state': {'reference': refs[0], 'scene': refs[1]},
                'assets': {refs[0]: reference, refs[1]: scene},
                'questions': {'target': {'type': 'choice', 'instructions': prompt, 'criteria': CRITERIA}}}
        url = 'https://api.typesafe.ai/v1/systemone'
        headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'TypeSafe-Danger-Zone-Images': 'true'}
    elif model == 'Clef':
        account, token = read_setting('CLOUDFLARE_ACCOUNT_ID'), read_setting('CLOUDFLARE_API_TOKEN')
        if not token or not re.fullmatch(r'[0-9a-fA-F]{32}', account):
            raise RuntimeError('Cloudflare credentials missing or invalid')
        prompt = PROMPT
        body = {'model': 'clef', 'images': ['data:image/jpeg;base64,' + reference['data_base64'],
                                              'data:image/jpeg;base64,' + scene['data_base64']],
                'state': STATE, 'questions': {'target': {'type': 'choice', 'instructions': prompt, 'criteria': CRITERIA}}}
        url = f'https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/cloudflare/clef'
        headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
    else:
        raise ValueError('unknown model')
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method='POST')
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'{model} API HTTP {exc.code}') from None
    elapsed = time.perf_counter() - start
    result = data if model == 'Jev' else data.get('result', {})
    if (model == 'Clef' and not data.get('success')) or result.get('model') != ('jev-1.14.0' if model == 'Jev' else 'clef'):
        raise RuntimeError(f'{model} response model or status is invalid')
    answer = result.get('answers', {}).get('target', {})
    if answer.get('choice') not in CRITERIA:
        raise RuntimeError(f'{model} returned an invalid choice')
    confidence = answer.get('confidence')
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        confidence = None
    return {'choice': answer['choice'], 'confidence': confidence, 'seconds': elapsed, 'prompt': prompt,
            'prepared_sha256': {k: hashlib.sha256(base64.b64decode(v['data_base64'])).hexdigest()
                                for k, v in [('reference', reference), ('scene', scene)]},
            'usage': result.get('usage')}


def main():
    now = datetime.datetime.now().astimezone()
    path = ROOT / 'results' / f'presence_pilot_{now:%Y%m%d_%H%M%S}.json'
    examples = [(f'data/stages_v3/{s["image"]}', 'present') for s in STAGES]
    examples += [(f'data/backgrounds/stage{i}.png', 'absent') for i in range(1, 6)]
    report = {'started_at': now.isoformat(), 'task': 'presence, not localization', 'criteria': CRITERIA,
              'clef_state': STATE, 'examples': examples, 'rows': []}
    for scene, truth in examples:
        for model in ('Jev', 'Clef'):
            try:
                row = {'model': model, 'scene': scene, 'expected': truth, **query(model, ROOT / scene)}
                row['correct'] = row['choice'] == truth
            except (RuntimeError, OSError, ValueError) as exc:
                row = {'model': model, 'scene': scene, 'expected': truth, 'error': str(exc)}
            report['rows'].append(row)
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(json.dumps({k: row[k] for k in ('model', 'scene', 'expected', 'choice', 'confidence', 'seconds', 'error') if k in row}, ensure_ascii=False), flush=True)
            if 'error' in row:
                print(f'Incomplete; saved {path}', flush=True)
                return
    print(f'Saved {path}', flush=True)


if __name__ == '__main__':
    main()
