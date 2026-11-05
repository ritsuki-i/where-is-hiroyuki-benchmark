"""Build a numbered sheet of YuNet detections for Jev to choose from."""
import math
from pathlib import Path
import cv2
from PIL import Image, ImageDraw, ImageFont, ImageOps
from face_search import detect_faces


def make_candidates(path):
    image, faces = detect_faces(path)
    height, width = image.shape[:2]
    if len(faces) > 254:
        raise RuntimeError(f'顔候補が{len(faces)}個あり、一度に選択できる上限254個を超えました')
    if not faces:
        return None, []
    cols = min(14, math.ceil(math.sqrt(len(faces)*1.15)))
    rows = math.ceil(len(faces)/cols)
    tile = min(110, 1568//max(cols, rows))
    sheet = Image.new('RGB', (cols*tile, rows*tile), 'white')
    draw = ImageDraw.Draw(sheet)
    fontfile = Path('C:/Windows/Fonts/arial.ttf')
    font = ImageFont.truetype(str(fontfile), max(10, tile//7)) if fontfile.exists() else ImageFont.load_default()
    rgb = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    boxes = []
    for index, face in enumerate(faces):
        x, y, w, h = map(float, face[:4])
        x1, y1, x2, y2 = max(0, x), max(0, y), min(width, x+w), min(height, y+h)
        if x2 <= x1 or y2 <= y1:
            raise RuntimeError('YuNetが無効な顔枠を返しました')
        boxes.append([x1/width, y1/height, x2/width, y2/height])
        left, top = (index % cols)*tile, (index // cols)*tile
        # Modest padding retains face context; the returned box remains YuNet's original box.
        pad = 0.2*max(w,h)
        crop = rgb.crop((max(0, int(x1-pad)), max(0, int(y1-pad)), min(width, math.ceil(x2+pad)), min(height, math.ceil(y2+pad))))
        crop = ImageOps.contain(crop, (tile-4, tile-25), Image.Resampling.LANCZOS)
        sheet.paste(crop, (left+(tile-crop.width)//2, top+22+(tile-25-crop.height)//2))
        draw.text((left+3, top+2), f'face_{index+1:03d}', fill='black', font=font)
    return sheet, boxes
