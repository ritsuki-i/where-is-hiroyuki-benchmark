"""Capture a race's exact displayed outcomes and reproducibility metadata."""
import datetime
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('Jev', 'Clef', 'Opus 5.5', 'YuNet + SFace')
START = '<!-- BEGIN LATEST RACE -->'
END = '<!-- END LATEST RACE -->'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(reference, stages):
    paths = ['benchmark_protocol.json','scripts/server.py','scripts/race_records.py',
             'scripts/face_search.py','viewer/race.js','viewer/race.html','viewer/race.css',
             'data/stages_v3/annotations_draft.json','models/yunet.onnx','models/sface.onnx']
    paths += [str(reference.relative_to(ROOT)).replace('\\','/')]
    paths += [f"data/stages_v3/{stage['image']}" for stage in stages]
    hashes = {path:sha(ROOT/path) if (ROOT/path).is_file() else None for path in paths}
    versions = {}
    for package in ('Pillow','opencv-python','numpy'):
        try: versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: versions[package] = None
    revision = None
    code_dirty = None
    try:
        revision = subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,timeout=5,check=True).stdout.strip()
        code_paths = ['benchmark_protocol.json','scripts/server.py','scripts/race_records.py',
                      'scripts/face_search.py','viewer/race.js','viewer/race.html','viewer/race.css']
        tracked = subprocess.run(['git','ls-files','--error-unmatch',*code_paths],cwd=ROOT,capture_output=True,timeout=5)
        diff = subprocess.run(['git','diff','--quiet','HEAD','--',*code_paths],cwd=ROOT,capture_output=True,timeout=5)
        code_dirty = tracked.returncode != 0 or diff.returncode != 0
    except (OSError,subprocess.SubprocessError):
        pass
    cli_version = None
    cli = shutil.which('claude.cmd') or shutil.which('claude')
    if cli:
        try:
            result = subprocess.run([cli,'--version'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=10)
            if result.returncode==0:
                cli_version=result.stdout.strip()[:100]
        except (OSError,subprocess.SubprocessError):
            pass
    return {'protocol':json.loads((ROOT/'benchmark_protocol.json').read_text(encoding='utf-8')),
            'sha256':hashes,'environment':{'python':sys.version.split()[0],
            'platform':platform.platform(),'packages':versions,'claude_code_version':cli_version,
            'git_revision':revision,'protocol_code_uncommitted':code_dirty,
            'race_port':os.environ.get('RACE_PORT','8765')}}


def validate(payload, stages, score_box, protocol):
    run_id = payload.get('run_id')
    if not isinstance(run_id,str) or not re.fullmatch(r'[0-9a-f]{32}',run_id):
        raise ValueError('invalid run id')
    models = payload.get('models')
    if not isinstance(models,list) or len(models)!=len(NAMES):
        raise ValueError('invalid models')
    clean = []
    for expected, item in zip(NAMES,models):
        if not isinstance(item,dict) or item.get('name')!=expected:
            raise ValueError('invalid model name')
        status = item.get('status')
        if status not in ('completed','error','skipped','unsupported'):
            raise ValueError('invalid model status')
        elapsed = item.get('elapsed_text')
        if status in ('completed','error'):
            if not isinstance(elapsed,str) or not re.fullmatch(r'\d{1,6}\.\d{2}',elapsed):
                raise ValueError('invalid displayed time')
        elif elapsed is not None:
            raise ValueError('invalid time for unrun model')
        rows = item.get('stages')
        if not isinstance(rows,list) or len(rows)>len(stages):
            raise ValueError('invalid stages')
        if status == 'completed' and len(rows)!=len(stages):
            raise ValueError('completed run must contain all stages')
        if status in ('skipped','unsupported') and rows:
            raise ValueError('unrun model cannot contain stages')
        checked = []
        for i,row in enumerate(rows):
            if not isinstance(row,dict) or row.get('stage')!=i+1:
                raise ValueError('invalid stage order')
            stage_seconds = row.get('stage_wall_seconds')
            if isinstance(stage_seconds,bool) or not isinstance(stage_seconds,(int,float)) or not math.isfinite(stage_seconds) or stage_seconds<0:
                raise ValueError('invalid stage time')
            if 'error' in row:
                if status!='error' or i!=len(rows)-1:
                    raise ValueError('invalid error position')
                checked.append({'stage':i+1,'error':str(row['error'])[:300],'stage_wall_seconds':stage_seconds})
                continue
            box = row.get('box')
            if box is not None and (not isinstance(box,list) or len(box)!=4 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1 for v in box) or box[0]>=box[2] or box[1]>=box[3]):
                raise ValueError('invalid box')
            score = score_box(box,stages[i])
            if row.get('correct') is not score['correct']:
                raise ValueError('score differs from protocol')
            expected_version={'Jev':'jev-1.14.0','Clef':'@cf/cloudflare/clef','Opus 5.5':'claude-opus-5-5','YuNet + SFace':'YuNet + SFace'}.get(expected)
            if row.get('model') != expected_version:
                raise ValueError('response model differs from protocol')
            prepared = row.get('prepared_sha256')
            prompt = row.get('prompt')
            if expected in ('Jev','Clef','Opus 5.5'):
                if not isinstance(prompt,str) or len(prompt)>5000 or not isinstance(prepared,dict) or set(prepared)!={'reference','scene'} or any(not isinstance(value,str) or not re.fullmatch(r'[0-9a-f]{64}',value) for value in prepared.values()):
                    raise ValueError('missing direct-model prompt or image hashes')
                if expected == 'Jev' and prompt != protocol['prompt']+' '+protocol['models']['Jev']['prompt_suffix']:
                    raise ValueError('Jev prompt differs from protocol')
                if expected == 'Clef' and prompt != protocol['prompt']:
                    raise ValueError('Clef prompt differs from protocol')
                if expected == 'Opus 5.5' and (protocol['prompt'] not in prompt or not prompt.endswith(protocol['models']['Opus']['prompt_suffix'])):
                    raise ValueError('Opus prompt differs from protocol')
            choices=row.get('coordinate_choices')
            invalid=row.get('invalid_coordinates')
            if expected == 'Clef':
                fields=('left','top','right','bottom')
                if not isinstance(choices,dict) or set(choices)!=set(fields) or any(not isinstance(choices[name],str) or not re.fullmatch(r'p(?:0[0-9]{2}|100)',choices[name]) for name in fields):
                    raise ValueError('invalid Clef coordinate choices')
                coords=[int(choices[name][1:])*protocol['models']['Clef']['coordinate_step'] for name in fields]
                is_invalid=coords[0]>=coords[2] or coords[1]>=coords[3]
                if invalid is not is_invalid or box != (None if is_invalid else coords):
                    raise ValueError('Clef box differs from chosen coordinates')
                spec=protocol['models']['Clef']
                expected_questions={name:spec['question_template'].format(task=protocol['prompt'],description=spec['coordinate_fields'][name]) for name in fields}
                if row.get('coordinate_questions') != expected_questions:
                    raise ValueError('Clef questions differ from protocol')
            checked.append({'stage':i+1,'box':box,**score,'stage_wall_seconds':stage_seconds,
                            'backend_seconds':row.get('seconds'),'candidates':row.get('candidates'),
                            'prompt':prompt,'prepared_sha256':prepared,
                            'coordinate_choices':choices,'coordinate_questions':row.get('coordinate_questions'),'axis_confidence':row.get('axis_confidence'),
                            'invalid_coordinates':invalid,'usage':row.get('usage'),
                            'confidence':row.get('confidence'),
                            'model':str(row.get('model',''))[:100]})
        if status=='error' and (not checked or 'error' not in checked[-1]):
            raise ValueError('missing error')
        clean.append({'name':expected,'status':status,'elapsed_text':elapsed,
                      'successes':sum(bool(r.get('correct')) for r in checked),
                      'completed_stages':sum('error' not in r for r in checked),'stages':checked})
    for i in range(len(stages)):
        prepared=[model['stages'][i]['prepared_sha256'] for model in clean[:3]
                  if i<len(model['stages']) and 'error' not in model['stages'][i]]
        if prepared and any(value!=prepared[0] for value in prepared[1:]):
            raise ValueError('direct-model prepared images differ')
    return run_id,clean


def save(payload, reference, stages, score_box):
    current = snapshot(reference,stages)
    if payload.get('sha256') != current['sha256']:
        raise ValueError('実行中に設定・コード・入力が変わったため保存できません。再起動して再実行してください')
    run_id,models = validate(payload,stages,score_box,current['protocol'])
    record = {'run_id':run_id,'recorded_at':datetime.datetime.now().astimezone().isoformat(),
              'snapshot':current,'models':models}
    out = ROOT/'results'/f'race_{run_id}.json'
    if out.exists():
        raise ValueError('run already saved')
    readme = ROOT/'README.md'
    source = readme.read_text(encoding='utf-8')
    if source.count(START)!=1 or source.count(END)!=1 or source.index(START)>source.index(END):
        raise RuntimeError('READMEの結果欄を更新できません')
    lines = [f'実行ID：`{run_id}`', '',f"実行条件：`{current['protocol']['protocol_id']}`", '',f"保存日時：{record['recorded_at']}", '',
             '| 手法 | 正解 | 画面の時間 | 状態 |','|---|---:|---:|---|']
    labels={'completed':'完了','error':'エラーで中断','skipped':'未実行','unsupported':'未対応'}
    for item in models:
        score = f"{item['successes']} / 5" if item['status']=='completed' else (f"{item['successes']} / 5（未完了）" if item['status']=='error' else '—')
        elapsed = item['elapsed_text']+'秒' if item['elapsed_text'] is not None else '—'
        lines.append(f"| {item['name']} | {score} | {elapsed} | {labels[item['status']]} |")
    run_dir = ROOT/'docs'/'runs'/run_id
    if run_dir.exists():
        raise ValueError('run images already exist')
    render_run(run_dir,run_id,models,stages)
    lines += ['',f'[この実行のステージ別予測画像](docs/runs/{run_id}/index.md)', '',
              f'実行時の設定・画像・コードのSHA-256、予測枠と各ステージの結果はローカルの `results/race_{run_id}.json` に保存しています。',
              '画面に表示した時間と正解数を記録しています。Clefは単体で4座標を選択し、不正な座標は補正せず不正解としています。']
    updated=source[:source.index(START)]+START+'\n'+'\n'.join(lines)+'\n'+source[source.index(END):]
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    readme.write_text(updated,encoding='utf-8')
    return {'run_id':run_id,'result_file':f'results/{out.name}'}


def render_run(directory,run_id,models,stages):
    """Render only predictions from this saved run, with missing runs explicit."""
    directory.mkdir(parents=True,exist_ok=False)
    font_path=Path('C:/Windows/Fonts/arial.ttf')
    font=ImageFont.truetype(str(font_path),24) if font_path.exists() else ImageFont.load_default()
    index=['# このレースのステージ別結果','',f'実行ID：`{run_id}`','',
           '赤は予測顔枠、黄は概算の正解顔枠。未実行、エラー、非対応は予測として扱いません。','']
    for i,stage in enumerate(stages):
        image=Image.open(ROOT/'data/stages_v3'/stage['image']).convert('RGB')
        width,height=image.size
        panel_width=800
        panel_height=round(height*panel_width/width)
        header=46
        canvas=Image.new('RGB',(panel_width*2,(panel_height+header)*2),'#f5f2ea')
        draw=ImageDraw.Draw(canvas)
        notes=[]
        for j,model in enumerate(models):
            x=(j%2)*panel_width
            y=(j//2)*(panel_height+header)
            rows=model['stages']
            row=rows[i] if i<len(rows) else None
            if row is None or 'error' in row:
                status='ERROR' if row and 'error' in row else {'unsupported':'UNSUPPORTED','skipped':'NOT RUN'}.get(model['status'],'NO RESULT')
                draw.text((x+10,y+8),f"{model['name']} | {status}",font=font,fill='#171717')
                draw.rectangle((x,y+header,x+panel_width-1,y+header+panel_height-1),fill='#e8e8e8')
                notes.append(f"- {model['name']}：{status}")
                continue
            panel=image.copy()
            pen=ImageDraw.Draw(panel)
            for box,color in ((row['target_box'],'#ffd83d'),(row['box'],'#ff4040')):
                if box:
                    coords=tuple(round(value*size) for value,size in zip(box,(width,height,width,height)))
                    pen.rectangle(coords,outline='black',width=8)
                    pen.rectangle(coords,outline=color,width=5)
            panel.thumbnail((panel_width,panel_height),Image.Resampling.LANCZOS)
            canvas.paste(panel,(x,y+header))
            status='MATCH' if row['correct'] else ('MISS: invalid box' if row.get('invalid_coordinates') else 'MISS: no box' if row['box'] is None else 'MISS')
            draw.text((x+10,y+8),f"{model['name']} | {status}",font=font,fill='#171717')
            notes.append(f"- {model['name']}：{'正解' if row['correct'] else '不正解（座標が不正・未補正）' if row.get('invalid_coordinates') else '不正解'}")
        canvas.save(directory/f'stage{i+1}.jpg',quality=90)
        page=[f'# ステージ{i+1}','',f'実行ID：`{run_id}`','',
              f'![この実行のステージ{i+1}の予測](stage{i+1}.jpg)','',*notes,'',
              '[この実行の一覧](index.md)']
        (directory/f'stage{i+1}.md').write_text('\n'.join(page)+'\n',encoding='utf-8')
        index.append(f'- [ステージ{i+1}](stage{i+1}.md)')
    index += ['','[READMEに戻る](../../../README.md)']
    (directory/'index.md').write_text('\n'.join(index)+'\n',encoding='utf-8')
