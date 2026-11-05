"""Evaluate an external model command; each invocation receives only a stage image."""
import argparse, json, subprocess, sys, tempfile, time
from pathlib import Path
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]

def evaluate(mask_path, gt_path):
    pred = Image.open(mask_path).convert('L')
    gt = Image.open(gt_path).convert('L')
    if pred.size != gt.size: raise ValueError(f'output dimensions {pred.size} != {gt.size}')
    pred = pred.point(lambda p: 255 if p >= 128 else 0)
    gt = gt.point(lambda p: 255 if p >= 128 else 0)
    intersection = sum(ImageChops.darker(pred, gt).histogram()[255:])
    union = sum(ImageChops.lighter(pred, gt).histogram()[255:])
    return intersection/union if union else 1.0

def main():
    p = argparse.ArgumentParser(description='Command arguments after -- are run with IMAGE OUTPUT_MASK appended.')
    p.add_argument('--name', required=True)
    p.add_argument('--timeout', type=float, default=300)
    p.add_argument('command', nargs=argparse.REMAINDER)
    args = p.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command: p.error('provide a model command after --')
    manifest = json.loads((ROOT/'data/annotations/manifest.json').read_text(encoding='utf-8'))
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for item in manifest:
            output = Path(tmp)/(item['id']+'.png')
            start = time.perf_counter()
            try:
                proc = subprocess.run(command+[str(ROOT/item['image']), str(output)], capture_output=True, text=True, timeout=args.timeout, cwd=ROOT)
                elapsed = time.perf_counter()-start
                if proc.returncode: raise RuntimeError(f'exit {proc.returncode}: {proc.stderr[-500:]}')
                if not output.exists(): raise RuntimeError('output mask missing')
                iou = evaluate(output, ROOT/item['mask'])
                rows.append({'stage':item['id'], 'seconds':elapsed, 'iou':iou, 'success':iou >= 0.5, 'error':None})
            except (subprocess.TimeoutExpired, OSError, ValueError, RuntimeError) as e:
                rows.append({'stage':item['id'], 'seconds':time.perf_counter()-start, 'iou':0.0, 'success':False, 'error':str(e)})
    result = {'model':args.name, 'protocol': 'one fresh process per stage; wall clock includes startup; IoU threshold 0.5', 'stages':rows, 'mean_iou':sum(r['iou'] for r in rows)/len(rows), 'successes':sum(r['success'] for r in rows), 'total_seconds':sum(r['seconds'] for r in rows)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if any(r['error'] for r in rows) else 0

if __name__ == '__main__': sys.exit(main())
