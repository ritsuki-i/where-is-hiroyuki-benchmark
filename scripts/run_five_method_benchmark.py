"""Repeat the face benchmark including Opus; save successes and errors incrementally."""
import datetime
import json
import time
from server import ROOT, run_face, run_jev, run_jev_candidates, run_opus, run_sonnet


def main():
    stamp = datetime.datetime.now().astimezone().strftime('%Y%m%d_%H%M%S')
    path = ROOT/'results'/f'five_method_benchmark_{stamp}.json'
    path.parent.mkdir(exist_ok=True)
    report = {'started_at':datetime.datetime.now().astimezone().isoformat(),
              'dataset':'data/stages_v3',
              'rule':'predicted face box center lies inside approximate ground-truth face box',
              'timing':'sequential calls, wall time includes preparation, model startup, and communication',
              'models':{}}
    for name, run in [('Jev',run_jev),('Sonnet 5.5',run_sonnet),('Opus',run_opus),('YuNet + SFace',run_face),('YuNet + Jev',run_jev_candidates)]:
        model = report['models'][name] = {'stages':[]}
        for index in range(5):
            start = time.perf_counter()
            try:
                result = run(index)
            except Exception as exc:
                result = {'error':str(exc)}
            result['wall_seconds'] = time.perf_counter()-start
            model['stages'].append({'stage':index+1, **result})
            completed = [row for row in model['stages'] if 'error' not in row]
            model.update(completed=len(completed), successes=sum(bool(row.get('correct')) for row in completed),
                         total_wall_seconds=sum(row['wall_seconds'] for row in model['stages']))
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(name, json.dumps(model['stages'][-1], ensure_ascii=False), flush=True)
        print(f'Saved: {path}',flush=True)


if __name__ == '__main__':
    main()
