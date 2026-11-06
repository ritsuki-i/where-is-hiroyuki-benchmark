"""Render archived four-method predictions as one 2x2 image per stage."""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'docs/media'
FIVE = ROOT/'results/five_method_benchmark_20261105_155632.json'
CLEF = ROOT/'results/clef_benchmark_20261106_012705.json'


def main():
    archived = json.loads(FIVE.read_text(encoding='utf-8'))['models']
    clef = json.loads(CLEF.read_text(encoding='utf-8'))['stages']
    font_path = Path('C:/Windows/Fonts/arial.ttf')
    font = ImageFont.truetype(str(font_path), 28) if font_path.exists() else ImageFont.load_default()
    OUT.mkdir(parents=True,exist_ok=True)
    for i in range(5):
        image = Image.open(ROOT/f'data/stages_v3/stage{i+1}.png').convert('RGB')
        width, height = image.size
        rows = [('Jev 1.14.0',archived['Jev']['stages'][i]),
                ('Clef',None),
                ('Claude Opus 5.5',archived['Opus']['stages'][i]),
                ('YuNet + SFace',archived['YuNet + SFace']['stages'][i])]
        panel_width = 900
        panel_height = round(height*panel_width/width)
        title_height = 50
        canvas = Image.new('RGB',(panel_width*2,(panel_height+title_height)*2),'#f5f2ea')
        draw = ImageDraw.Draw(canvas)
        for j,(name,row) in enumerate(rows):
            x=(j%2)*panel_width
            y=(j//2)*(panel_height+title_height)
            if row is None:
                draw.text((x+12,y+8),'Clef  |  BOX UNSUPPORTED',font=font,fill='#171717')
                draw.rectangle((x,y+title_height,x+panel_width-1,y+title_height+panel_height-1),fill='#e8e8e8')
                draw.text((x+35,y+title_height+45),'No standalone result under Jev Box protocol',font=font,fill='#444444')
                continue
            if 'error' in row:
                raise RuntimeError(f'{name} stage {i+1} has no prediction')
            panel = image.copy()
            pen = ImageDraw.Draw(panel)
            for box,color in [(row['target_box'],'#ffd83d'),(row.get('box'),'#ff4040')]:
                if box:
                    coords = tuple(round(v*s) for v,s in zip(box,(width,height,width,height)))
                    pen.rectangle(coords,outline='black',width=8)
                    pen.rectangle(coords,outline=color,width=5)
            panel.thumbnail((panel_width,panel_height),Image.Resampling.LANCZOS)
            status='MATCH' if row['correct'] else ('MISS: none selected' if row.get('box') is None else 'MISS')
            draw.text((x+12,y+8),f'{name}  |  {status}  |  {row["wall_seconds"]:.2f} s',font=font,fill='#171717')
            canvas.paste(panel,(x,y+title_height))
        canvas.save(OUT/f'comparison-stage{i+1}.jpg',quality=91)
        notes = [f'- {name}：未測定（Box形式非対応）' if row is None else f'- {name}：{"正解" if row["correct"] else "不正解"}（{row["wall_seconds"]:.2f}秒）' for name,row in rows]
        page = [f'# ステージ{i+1}：4手法の推論結果','',
                '左上からJev、Clef単体、Claude Opus 5.5、YuNet + SFace。赤が予測枠、黄色が概算の正解顔枠です。Clefは同じBox形式に対応せず未測定です。','',
                f'![ステージ{i+1}の4手法の予測と正解](media/comparison-stage{i+1}.jpg)','',*notes,'',
                '正解は予測枠の中心が概算の正解顔枠に入るかで判定しています。Jev・Opus・SFaceは11月5日の測定で、時間には準備・通信・起動を含みます。YuNet + Clefは別の補助実験です。','',
                'このページのJevは顔枠を指示した保存済みの実験結果です。現在のレース画面のJevは人物の可視部分を予測し、人物枠で判定します。','',
                '[全ステージ一覧](inference-results.md) ｜ [READMEに戻る](../README.md)']
        (ROOT/f'docs/stage{i+1}.md').write_text('\n'.join(page)+'\n',encoding='utf-8')
        row=clef[i]
        panel=image.copy()
        pen=ImageDraw.Draw(panel)
        for box,color in [(row['target_box'],'#ffd83d'),(row.get('box'),'#ff4040')]:
            if box:
                coords=tuple(round(v*s) for v,s in zip(box,(width,height,width,height)))
                pen.rectangle(coords,outline='black',width=8)
                pen.rectangle(coords,outline=color,width=5)
        panel.thumbnail((panel_width,panel_height),Image.Resampling.LANCZOS)
        supplement=Image.new('RGB',(panel_width,panel_height+title_height),'#f5f2ea')
        supplement.paste(panel,(0,title_height))
        status='MATCH' if row['correct'] else 'MISS'
        ImageDraw.Draw(supplement).text((12,8),f'YuNet + Clef  |  {status}  |  {row["wall_seconds"]:.2f} s',font=font,fill='#171717')
        supplement.save(OUT/f'clef-candidates-stage{i+1}.jpg',quality=91)


if __name__ == '__main__':
    main()
