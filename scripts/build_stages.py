"""Compose the supplied character over generated scenes and record exact masks."""
from pathlib import Path
from collections import deque
import json
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SIZES = [330, 240, 170, 120, 85]
POSITIONS = [(0.17, 0.58), (0.72, 0.57), (0.39, 0.67), (0.75, 0.70), (0.23, 0.72)]

def cutout(path):
    image = Image.open(path).convert('RGBA')
    pixels = image.load()
    w, h = image.size
    # Remove only light pixels connected to the outside, preserving interior whites.
    seen = bytearray(w*h)
    q = deque()
    def add(x, y):
        i = y*w+x
        if not seen[i] and min(pixels[x,y][:3]) >= 235:
            seen[i] = 1
            q.append((x,y))
    for x in range(w): add(x,0); add(x,h-1)
    for y in range(h): add(0,y); add(w-1,y)
    while q:
        x,y = q.popleft()
        pixels[x,y] = (0,0,0,0)
        for nx,ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if 0 <= nx < w and 0 <= ny < h: add(nx,ny)
    return image.crop(image.getchannel('A').getbbox())

def main():
    source = next((ROOT/'hiroyuki').glob('*.png'))
    target = cutout(source)
    manifest = []
    for i, (height, position) in enumerate(zip(SIZES, POSITIONS), 1):
        bg = Image.open(ROOT/f'data/backgrounds/stage{i}.png').convert('RGB')
        w,h = bg.size
        sprite = target.resize((round(target.width*height/target.height), height), Image.Resampling.LANCZOS)
        x = min(w-sprite.width, max(0, round(position[0]*w-sprite.width/2)))
        y = min(h-sprite.height, max(0, round(position[1]*h-sprite.height/2)))
        mask = Image.new('L', bg.size, 0)
        mask.paste(sprite.getchannel('A'), (x,y))
        # Binary mask is the actual composited foreground, thresholded at 128.
        mask = mask.point(lambda p: 255 if p >= 128 else 0)
        bg.paste(sprite, (x,y), sprite)
        bg.save(ROOT/f'data/stages/stage{i}.png')
        mask.save(ROOT/f'data/annotations/stage{i}_mask.png')
        bbox = mask.getbbox()
        manifest.append({'id': f'stage{i}', 'image': f'data/stages/stage{i}.png', 'mask': f'data/annotations/stage{i}_mask.png', 'width':w, 'height':h, 'bbox_xyxy_exclusive':list(bbox), 'target_count':1, 'sprite_height_px':height})
    (ROOT/'data/annotations/manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

if __name__ == '__main__': main()
