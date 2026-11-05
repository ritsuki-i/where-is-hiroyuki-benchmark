"""Create provisional GrabCut masks for visual review, not final ground truth."""
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / 'data/stages_v3'
out = ROOT / 'data/annotations_v3_draft'
out.mkdir(exist_ok=True)
data = json.loads((source/'annotations_draft.json').read_text(encoding='utf-8'))
panels = []
for item in data['stages']:
    image = cv2.imread(str(source/item['image']))
    x1,y1,x2,y2 = item['bbox_xyxy_approx']
    # A small margin supplies background examples; no ground truth is assumed.
    pad = 8
    x,y = max(0,x1-pad),max(0,y1-pad)
    x2,y2 = min(item['width']-1,x2+pad),min(item['height']-1,y2+pad)
    seg = np.zeros(image.shape[:2],np.uint8)
    cv2.grabCut(image,seg,(x,y,x2-x,y2-y),None,None,5,cv2.GC_INIT_WITH_RECT)
    mask = np.where((seg==cv2.GC_FGD)|(seg==cv2.GC_PR_FGD),255,0).astype('uint8')
    cv2.imwrite(str(out/(item['id']+'_mask.png')),mask)
    overlay=image.copy()
    overlay[mask>0] = (overlay[mask>0]*0.55 + np.array([40,40,230])*0.45).astype('uint8')
    rgb = cv2.cvtColor(overlay[y:y2,x:x2],cv2.COLOR_BGR2RGB)
    panel=Image.fromarray(rgb)
    panel.thumbnail((260,420))
    panels.append((item['id'],panel))
sheet=Image.new('RGB',(260*5,470),'white')
draw=ImageDraw.Draw(sheet)
for i,(name,panel) in enumerate(panels):
    draw.text((i*260+5,5),name,fill='black')
    sheet.paste(panel,(i*260,30))
sheet.save(out/'review.png')
