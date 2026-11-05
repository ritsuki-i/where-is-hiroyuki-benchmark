"""Render publication images from the saved face-benchmark results."""
import json
import shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/media'
RESULT = ROOT / 'results/face_benchmark_20261105_135020.json'
NAMES = ['Jev', 'Sonnet 5.5', 'YuNet + SFace']


def rect_pixels(box, width, height):
    return (round(box[0]*width), round(box[1]*height), round(box[2]*width), round(box[3]*height))


def outlined(draw, box, color, width=4):
    draw.rectangle(box, outline='black', width=width+3)
    draw.rectangle(box, outline=color, width=width)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = json.loads(RESULT.read_text(encoding='utf-8'))
    shutil.copyfile(next((ROOT/'hiroyuki').glob('*.png')), OUT/'reference.png')
    font_path = Path('C:/Windows/Fonts/arial.ttf')
    font = ImageFont.truetype(str(font_path), 20) if font_path.exists() else ImageFont.load_default()
    target = report['models']['Jev']['stages'][0]['target_box']
    scene = Image.open(ROOT/'data/stages_v3/stage1.png').convert('RGB')
    outlined(ImageDraw.Draw(scene), rect_pixels(target, *scene.size), '#ffdb42', 5)
    # Add a magnified detail without hiding any of the scene.
    x1, y1, x2, y2 = rect_pixels(target, *scene.size)
    detail = scene.crop((max(0, x1-65), max(0, y1-65), min(scene.width, x2+65), min(scene.height, y2+65)))
    detail.thumbnail((350, 350), Image.Resampling.LANCZOS)
    overview = Image.new('RGB', (scene.width+390, scene.height), '#f5f2ea')
    overview.paste(scene, (0, 0))
    ImageDraw.Draw(overview).text((scene.width+20, 20), 'FACE DETAIL', font=font, fill='#171717')
    overview.paste(detail, (scene.width+20, 55))
    overview.save(OUT/'ground-truth-stage1.jpg', quality=90)

    for i in range(5):
        scene = Image.open(ROOT/f'data/stages_v3/stage{i+1}.png').convert('RGB')
        width, height = scene.size
        panel_width = 720
        panel_height = round(height * panel_width / width)
        canvas = Image.new('RGB', (panel_width*3, panel_height+50), '#f5f2ea')
        draw = ImageDraw.Draw(canvas)
        for j, name in enumerate(NAMES):
            row = report['models'][name]['stages'][i]
            panel = scene.copy()
            pen = ImageDraw.Draw(panel)
            outlined(pen, rect_pixels(row['target_box'], width, height), '#ffdb42', 5)
            if row['box']:
                outlined(pen, rect_pixels(row['box'], width, height), '#ff4949', 5)
            panel = panel.resize((panel_width, panel_height), Image.Resampling.LANCZOS)
            canvas.paste(panel, (j*panel_width, 50))
            status = 'MATCH' if row['correct'] else 'MISS'
            draw.text((j*panel_width+12, 13), f'{name}  |  {status}  |  {row["wall_seconds"]:.2f} s', font=font, fill='#171717')
        canvas.save(OUT/f'results-stage{i+1}.jpg', quality=90)


if __name__ == '__main__':
    main()
