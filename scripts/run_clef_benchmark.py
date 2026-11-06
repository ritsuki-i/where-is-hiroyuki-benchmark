"""Evaluate YuNet + Cloudflare Clef and save each stage incrementally."""
import datetime
import json
import time
from server import ROOT, run_clef_candidates


def main():
    now = datetime.datetime.now().astimezone()
    path = ROOT/'results'/f'clef_benchmark_{now:%Y%m%d_%H%M%S}.json'
    path.parent.mkdir(exist_ok=True)
    report = {'started_at':now.isoformat(), 'model':'@cf/cloudflare/clef',
              'method':'YuNet face candidates + Clef choice', 'dataset':'data/stages_v3',
              'rule':'predicted face box center lies inside approximate ground-truth face box',
              'timing':'sequential wall time includes face detection, image preparation and API', 'stages':[]}
    for index in range(5):
        started = time.perf_counter()
        try:
            result = run_clef_candidates(index)
        except Exception as exc:
            result = {'error':str(exc)}
        result['wall_seconds'] = time.perf_counter()-started
        report['stages'].append({'stage':index+1, **result})
        completed = [row for row in report['stages'] if 'error' not in row]
        report.update(completed=len(completed), successes=sum(bool(row.get('correct')) for row in completed),
                      total_wall_seconds=sum(row['wall_seconds'] for row in report['stages']))
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report['stages'][-1],ensure_ascii=False),flush=True)
        if 'error' in result:
            break
    print(f'Saved: {path}',flush=True)


if __name__ == '__main__':
    main()
