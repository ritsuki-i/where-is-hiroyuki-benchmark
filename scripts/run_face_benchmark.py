"""Run and save the three-method face benchmark, including errors and timings."""
import datetime
import json
import time
from pathlib import Path

from server import run_face, run_jev, run_sonnet

ROOT = Path(__file__).resolve().parents[1]


def main():
    output_dir = ROOT / 'results'
    output_dir.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().astimezone().strftime('%Y%m%d_%H%M%S')
    path = output_dir / f'face_benchmark_{stamp}.json'
    report = {'started_at': datetime.datetime.now().astimezone().isoformat(),
              'dataset': 'data/stages_v3',
              'rule': 'Jev: person coverage >= 0.5 and IoU >= 0.1; others: face box center inside approximate face box',
              'timing': 'wall time per call includes preparation and startup; models run sequentially',
              'models': {}}

    def save():
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    for name, run in [('Jev', run_jev), ('Sonnet 5.5', run_sonnet), ('YuNet + SFace', run_face)]:
        rows = []
        report['models'][name] = {'stages': rows}
        for index in range(5):
            start = time.perf_counter()
            try:
                result = run(index)
                result['wall_seconds'] = time.perf_counter() - start
            except Exception as exc:
                result = {'error': str(exc), 'wall_seconds': time.perf_counter() - start}
            rows.append({'stage': index+1, **result})
            save()
            print(f'{name} stage {index+1}: {json.dumps(rows[-1], ensure_ascii=False)}', flush=True)
        completed = [row for row in rows if 'error' not in row]
        report['models'][name].update(completed=len(completed), successes=sum(bool(row.get('correct')) for row in completed), total_wall_seconds=sum(row['wall_seconds'] for row in rows))
        save()
    print(f'Saved: {path}', flush=True)


if __name__ == '__main__':
    main()
