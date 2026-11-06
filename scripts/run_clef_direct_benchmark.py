"""Check standalone Clef on five stages without changing the latest race."""
import datetime
import json
import time
from server import ROOT, PROTOCOL, run_clef


def main():
    started=datetime.datetime.now().astimezone()
    path=ROOT/'results'/f'clef_direct_{started:%Y%m%d_%H%M%S}.json'
    path.parent.mkdir(exist_ok=True)
    report={'started_at':started.isoformat(),'protocol':PROTOCOL,'purpose':'standalone connectivity check, not a recorded video race','stages':[]}
    for index in range(5):
        begin=time.perf_counter()
        try:
            result=run_clef(index)
        except Exception as exc:
            result={'error':str(exc)}
        result['wall_seconds']=time.perf_counter()-begin
        report['stages'].append({'stage':index+1,**result})
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        row=report['stages'][-1]
        print(json.dumps({k:row[k] for k in ('stage','correct','box','invalid_coordinates','wall_seconds','error') if k in row},ensure_ascii=False),flush=True)
        if 'error' in result:
            break
    print(f'Saved: {path}',flush=True)


if __name__=='__main__':
    main()
