"""Evaluate GPT-6.1 Terra via ChatGPT-authenticated Codex with attached images."""
import datetime
import json
import math
import os
import shutil
import subprocess
import tempfile
import time
from server import ROOT, REFERENCE, STAGES, score_box


def main():
    cli = shutil.which('codex.cmd') or shutil.which('codex')
    if not cli:
        raise RuntimeError('Codex CLIが見つかりません')
    env = os.environ.copy()
    for name in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENAI_BASE_URL', 'OPENAI_ORG_ID', 'OPENAI_PROJECT_ID'):
        env.pop(name, None)
    auth = subprocess.run([cli, 'login', 'status'], capture_output=True, text=True, encoding='utf-8', errors='replace', env=env, timeout=30)
    if auth.returncode or 'Logged in using ChatGPT' not in (auth.stdout + auth.stderr):
        raise RuntimeError('ChatGPTサブスク認証を確認できません')
    stamp = datetime.datetime.now().astimezone().strftime('%Y%m%d_%H%M%S')
    path = ROOT/'results'/f'terra_benchmark_{stamp}.json'
    path.parent.mkdir(exist_ok=True)
    report = {'started_at':datetime.datetime.now().astimezone().isoformat(), 'model':'gpt-6.1-terra',
              'dataset':'data/stages_v3', 'reasoning_effort':'medium',
              'protocol':'Codex CLI ChatGPT login; two attached images; no external tools requested',
              'rule':'predicted face box center lies inside approximate ground-truth face box',
              'timing':'sequential wall time includes CLI startup and communication', 'stages':[]}
    prompt = ('The first attached image is a reference character, the second is a scene. '
              'Find the person in the scene whose face matches the reference; clothes and pose may differ. '
              'Give a tight bounding box around only the visible face of that person in the second image, '
              'not the body, as normalized 0 to 1 coordinates. Return JSON only: '
              '{"box": [left, top, right, bottom]}. Do not use any tools or read other files.')
    with tempfile.TemporaryDirectory(prefix='terra_benchmark_', dir=ROOT) as workdir:
        for index, stage in enumerate(STAGES):
            start = time.perf_counter()
            try:
                scene = ROOT/'data/stages_v3'/stage['image']
                args = [cli,'exec','--ignore-user-config','--ephemeral','--skip-git-repo-check',
                        '-s','read-only','-C',workdir,'-m','gpt-6.1-terra',
                        '-c','model_reasoning_effort="medium"','--json', prompt,
                        '-i',str(REFERENCE),'-i',str(scene)]
                proc = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', env=env, timeout=180)
                if proc.returncode:
                    raise RuntimeError('Codex実行失敗: '+proc.stderr[-500:])
                events = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
                if any(e.get('item',{}).get('type') not in (None,'agent_message','reasoning') for e in events):
                    raise RuntimeError('モデルがツールを使用したため評価対象外')
                messages = [e['item']['text'] for e in events if e.get('type') == 'item.completed' and e.get('item',{}).get('type') == 'agent_message']
                if not messages:
                    raise RuntimeError('Codexの最終回答がありません')
                parsed = None
                for offset, char in enumerate(messages[-1]):
                    if char == '{':
                        try:
                            value, _ = json.JSONDecoder().raw_decode(messages[-1][offset:])
                            if isinstance(value,dict) and 'box' in value:
                                parsed = value['box']
                                break
                        except json.JSONDecodeError:
                            pass
                if not isinstance(parsed,list) or len(parsed)!=4 or any(isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) or not 0<=n<=1 for n in parsed) or parsed[0]>=parsed[2] or parsed[1]>=parsed[3]:
                    raise RuntimeError('座標応答を解釈できません')
                result = {'box':parsed, **score_box(parsed,stage)}
            except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, RuntimeError) as exc:
                result = {'error':str(exc)}
            result['wall_seconds'] = time.perf_counter()-start
            report['stages'].append({'stage':index+1, **result})
            done = [x for x in report['stages'] if 'error' not in x]
            report.update(completed=len(done),successes=sum(bool(x.get('correct')) for x in done),total_wall_seconds=sum(x['wall_seconds'] for x in report['stages']))
            path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(report['stages'][-1],ensure_ascii=False),flush=True)
            if 'error' in result:
                break
    print(f'Saved: {path}',flush=True)


if __name__ == '__main__':
    main()
