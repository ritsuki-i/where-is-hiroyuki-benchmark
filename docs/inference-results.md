# 推論結果の画像

各ステージの左からJev、Sonnet 5.5、YuNet + SFaceの結果です。**赤が予測した顔枠、黄色が概算の正解顔枠**です。MATCHは中心位置による暫定正解、MISSは不正解を表します。画像を開くと拡大して確認できます。

**ステージ1**

![ステージ1の3手法の推論結果](media/results-stage1.jpg)

**ステージ2**

![ステージ2の3手法の推論結果](media/results-stage2.jpg)

**ステージ3**

![ステージ3の3手法の推論結果](media/results-stage3.jpg)

**ステージ4**

![ステージ4の3手法の推論結果](media/results-stage4.jpg)

**ステージ5**

![ステージ5の3手法の推論結果](media/results-stage5.jpg)

## YuNet + Jev：候補一覧からの選択

別の時刻に実施した追加実験です。黄色は正解顔枠、赤はYuNetから選ばれた顔枠を示します。ステージ3と5は「該当なし」を選んだため赤枠はありません。

**ステージ1**

![ステージ1のYuNetとJevによる結果](media/jev-candidates-stage1.jpg)

**ステージ2**

![ステージ2のYuNetとJevによる結果](media/jev-candidates-stage2.jpg)

**ステージ3**

![ステージ3のYuNetとJevによる結果](media/jev-candidates-stage3.jpg)

**ステージ4**

![ステージ4のYuNetとJevによる結果](media/jev-candidates-stage4.jpg)

**ステージ5**

![ステージ5のYuNetとJevによる結果](media/jev-candidates-stage5.jpg)

[READMEに戻る](../README.md)
