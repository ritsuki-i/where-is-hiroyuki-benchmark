# ひろゆきを探せ！ベンチマーク

人がたくさん描かれたイラストの中から、参照画像の「ひろゆき」を見つけられるか？

<img src="docs/media/reference.png" alt="探す対象のひろゆきの参照イラスト" width="240">

**探す対象：この人物の顔**

Jev、Clef単体、Claude Opus 5.5、顔検出・顔照合モデルのYuNet + SFaceを使い、5つのイラストで対象の顔を探します。Clef単体はJevと同じBox形式で実行できず、現在は未測定です。

![ステージ1の正解例。黄色の枠が目標の顔を示す](docs/media/ground-truth-stage1.jpg)

*正解の例：黄色い枠が探す顔の位置です。右側はその拡大図。正解枠は目視による概算です。*

> **この実験のメッセージ**：Jevは今回の計測で速かった一方、5枚のイラストから特定の顔の位置を返す課題では、求めた枠を正しく出せない例がありました。モデルには得意な仕事があり、目的に合った手法を選ぶことが大切です。
>
> この結果は画像5枚・各手法1回の小規模な試行です。実写や他のタスクでの一般的な性能を示すものではありません。

## プレイ動画 / GIF

**ここにレース画面の動画またはGIFを掲載予定。**

<!-- GIFを追加する場合、公開内容を確認して docs/media/race.gif に置き、次の行を有効にする。
![ひろゆきを探せ！ベンチマークの実行画面](docs/media/race.gif)
-->

<!-- 動画を追加する場合は docs/media/race.mp4 に置き、この位置にリンクを追加する。 -->

## 比較した4手法

| 手法 | 探し方 | 実行方法 |
|---|---|---|
| **Jev 1.14.0** | 参照画像とステージ画像を渡し、対象の位置をBox機能で直接予測。 | TypeSafe API |
| **Clef単体** | Jevと同じ画像・指示・Box形式での比較を試みたが、Box形式が非対応のため未測定。 | Cloudflare Workers AI `@cf/cloudflare/clef` |
| **Claude Opus 5.5** | 参照画像とステージ画像を読み、対象の顔枠を座標で予測。 | Claude Code、サブスク認証 |
| **YuNet + SFace** | YuNetで顔候補を検出し、SFaceで参照画像との顔の類似度が最も高い候補を選択。 | ローカル実行、追加学習なし |

CloudflareのClefは `choice`・`noul`・`score` に対応し、Jevの `box` 質問形式には対応していません。同じ画像で試したところ、BoxはHTTP 400で拒否され、Choiceは成功しました。[Cloudflare公式仕様](https://developers.cloudflare.com/workers-ai/models/clef/)も参照してください。YuNet + Clefは条件が異なるため、[補助実験](docs/additional-experiments.md)として分けています。

## 評価方法

- **入力**：同じ参照画像と5枚のステージ画像。正解の位置はモデルに渡していません。
- **正解判定**：予測した顔枠の中心が、目視で概算した正解の顔枠内にあれば正解。顔枠が出ない場合は不正解。
- **試行**：測定できた各手法について各ステージを1回ずつ実行。Jev・Opus・SFaceは11月5日に測定しました。Clef単体は未測定です。
- **時間**：各ステージの呼び出しにかかった経過時間。画像準備、モデルの読み込み、プロセス起動、API通信を含みます。画面上の並列レースとは測定条件が異なります。

**表示中の保存済み結果とレース画面のJevには違いがあります。** 表と画像のJevは「顔枠」を指示し、顔枠の中心で判定した過去の実験です。現在のレース画面のJevは**人物の可視部分**を予測し、人物の正解枠を50%以上覆い、IoUが0.1以上なら正解とします。他の3枠は顔枠の中心で判定するため、レース画面での正解数は同じ基準の比較ではありません。

正解枠は目視による下書きです。顔枠の中心だけを採点するため、大きすぎる枠でも中心が正解内なら正解になります。この正答率だけで枠の精密さまでは評価できません。

## 結果

| 手法 | 正解数 | 正答率 | 5問の合計時間 | 平均／問 |
|---|---:|---:|---:|---:|
| Jev 1.14.0 | 0 / 5 | 0% | 7.03秒 | 1.41秒 |
| Clef単体 | 未測定 | — | — | — |
| Claude Opus 5.5 | 4 / 5 | 80% | 53.72秒 | 10.74秒 |
| YuNet + SFace | 5 / 5 | 100% | 10.80秒 | 2.16秒 |

| 手法 | ステージ1 | ステージ2 | ステージ3 | ステージ4 | ステージ5 |
|---|:---:|:---:|:---:|:---:|:---:|
| Jev 1.14.0 | × | × | × | × | × |
| Clef単体 | — | — | — | — | — |
| Claude Opus 5.5 | ○ | ○ | ○ | ○ | × |
| YuNet + SFace | ○ | ○ | ○ | ○ | ○ |

**[4手法の予測枠を画像で見る：ステージ一覧](docs/inference-results.md)**

各ステージを2×2の画像にまとめています。[ステージ1](docs/stage1.md) ｜ [2](docs/stage2.md) ｜ [3](docs/stage3.md) ｜ [4](docs/stage4.md) ｜ [5](docs/stage5.md)

数値は通信状況や起動時間に影響されます。[詳細記録](results/five_method_benchmark_20261105_155632.md)も参照してください。生の結果JSONはローカルに保存しています。

## 考察

- **Jevは速かったが、この課題では失敗もあった。** 合計時間は7.03秒、顔枠の中心で判定すると0/5でした。ステージ1では対象を含む広い枠を返しましたが、枠の中心が顔の外にあったため不正解です。対象をまったく見つけられなかったことと、求めた顔枠を正確に返せなかったことは区別する必要があります。
- **このデータでは専用の顔検出・照合が強かった。** YuNet + SFaceは5/5で、Opusは4/5。ただし、YuNetが顔を検出できなければSFaceはその顔を選べません。
- **速さと適性を、目的に合わせて見る。** 短い時間で選択する処理と、画像内で小さな顔を見分ける処理では、必要な能力が異なります。Clef単体は未測定であり、この5枚からJevやClefの他のタスクでの性能は判断できません。
- **リアルタイム性は未検証。** 静止画を1枚ずつ処理した結果で、動画のFPSや監視カメラでの性能は測定していません。

Sonnet、GPT-6.1 Terra、YuNet + Jev、YuNet + Clefや前回の試行は[追加・補助実験](docs/additional-experiments.md)にまとめています。

## レース画面を動かす

Python 3.10以上、参照画像、5枚のステージ画像と注釈、YuNet・SFaceのモデルファイルが必要です。参照画像と評価データはGitに含まれません。Windows PowerShellでの準備例：

```powershell
python -m pip install -r requirements.txt
New-Item -ItemType Directory -Force models
Invoke-WebRequest 'https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx' -OutFile models/yunet.onnx
Invoke-WebRequest 'https://huggingface.co/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx' -OutFile models/sface.onnx
python scripts/server.py
```

`http://127.0.0.1:8765/` を開いてスタートします。赤が予測枠、黄色の点線が正解枠です。完了後はステージボタンで結果を確認できます。画面の結果は一時データで、再スタートや再読み込みで消えます。

Jevは画面のチェックを入れたときだけ実行します。Clef単体はBox形式非対応のため、画面では実行できないことを表示します。Jevには `.env.local` または環境変数の `TYPESAFE_API_KEY` が必要です。画像がAPIに送信され、利用料金が発生する場合があります。OpusはClaude Codeのサブスク認証を使用します。キーはサーバー側で扱い、画面には渡しません。

YuNet + Clefの補助評価は `python -X utf8 scripts/run_clef_benchmark.py` で実行でき、結果はローカルの `results/` に保存されます。Cloudflareの `CLOUDFLARE_API_TOKEN` と `CLOUDFLARE_ACCOUNT_ID` が必要で、料金が発生する場合があります。

## ファイルと共有方針

```text
scripts/     レース用サーバー、顔探索、評価スクリプト
viewer/      4手法のレース画面
docs/        ステージごとの結果画像と補助実験
results/     確認済みの結果要約と、ローカルの詳細結果
hiroyuki/    参照画像（Git管理外）
data/        評価画像・注釈など（Git管理外）
models/      ダウンロードしたモデルの重み（Git管理外）
```

README掲載用に選んだ画像と結果要約は共有対象です。認証情報、元の参照素材、評価データ、モデルの重み、生の結果JSONは`.gitignore`で除外しています。クローンだけでは評価を再現できません。`.env.example`には実際のキーを入れず、コミット前に差分を確認してください。
