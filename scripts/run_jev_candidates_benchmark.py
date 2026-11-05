"""Evaluate YuNet + Jev on the five face-search stages and save each result."""
import datetime
import json
import time
from server import ROOT, run_jev_candidates


def main():
    stamp = datetime.datetime.now().astimezone().strftime('%Y%m%d_%H%M%S')
    path = ROOT/'results'/f'jev_candidates_benchmark_{stamp}.json'
    path.parent.mkdir(exist_ok=True)
    report = {'started_at':datetime.datetime.now().astimezone().isoformat(),
              'method':'YuNet + Jev candidate sheet', 'dataset':'data/stages_v3',
              'rule':'predicted face box center lies inside approximate ground-truth face box',
              'timing':'wall time per call includes detection, preparation, and API request', 'stages':[]}
    for index in range(5):
        start = time.perf_counter()
        try:
            result = run_jev_candidates(index)
        except Exception as e:
            result = {'error':str(e)}
        result['wall_seconds'] = time.perf_counter()-start
        report['stages'].append({'stage':index+1, **result})
        completed = [row for row in report['stages'] if 'error' not in row]
        report.update(completed=len(completed), successes=sum(bool(row.get('correct')) for row in completed),
                      total_wall_seconds=sum(row['wall_seconds'] for row in report['stages']))
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2), encoding='utf-8')
        print(json.dumps(report['stages'][-1],ensure_ascii=False), flush=True)
    print(f'Saved: {path}', flush=True)


if __name__ == '__main__':
    main()
