---
name: pen-story-animation
description: 把分鏡圖、插圖加上故事腳本，做成「一支筆先勾線、再上色、畫完換頁」的筆繪說故事動畫 MP4，含中文旁白、字幕與音效。只要使用者給了圖片（一張多格分鏡或多張插圖）和故事、腳本、成語、寓言、繪本內容，並想要筆繪動畫、手繪動畫、塗鴉動畫、whiteboard animation、說故事影片、畫出來的動畫，就使用此技能；即使只說「照上次杯弓蛇影那樣做」或「把這張圖和腳本做成動畫」也一樣。沒有圖片、要用程式從零畫向量動畫，或要做原理解說片時不適用。
---

# 筆繪說故事動畫

輸入圖片和腳本，輸出 1080p MP4：畫面上只有一支筆，先勾線，再上色，停留後換頁。不要加手：手會遮住畫面，使用者已明確否決過。

需要：Windows、Python（opencv-python、numpy）、ffmpeg、Node、`npx hyperframes`。製作影片的硬性規則在 `/hyperframes`，動手前先讀。

## 流程

### 1. 建專案

HyperFrames 的部分指令遇到過長路徑會失敗，所以一律在短路徑製作，完成後再複製到使用者的資料夾。以下 `$W` 代表 `$TEMP/<英文短名>`，`<skill>` 代表本技能資料夾。

```bash
cd "$TEMP" && npx hyperframes init <英文短名> --example blank --non-interactive
```

把圖片複製到 `$W`，檔名改用英文。之後的指令都在 `$W` 執行。

### 2. 看圖，寫 story.json

先看過每張圖。若是一張多格分鏡，用 OpenCV 找出白色間隔，定出每格的 `crop`，往內縮 2 像素避免切到框線。

依腳本順序排格子，順序以劇情為準，不必照原圖位置。一段旁白若對應多格，就在逗號或句號處拆開，讓每格各有自己的旁白。

```json
{
  "source": "source.jpg",
  "tail": 2.2,
  "panels": [
    { "name": "title", "crop": [2, 2, 345, 379], "min": 3.4 },
    { "name": "see", "crop": [708, 2, 1054, 260], "narration": "朋友正要喝時，", "min": 3.4,
      "sfx": [{ "type": "heart", "span": 2, "vol": 0.9 }] },
    { "name": "drink", "image": "drink.png", "narration": "他只好硬著頭皮將蛇吞下肚。", "caption": "他只好硬著頭皮將「蛇」吞下肚。",
      "sfx": [{ "type": "gulp", "at": "voice_end", "offset": -0.1 }] }
  ]
}
```

欄位：
- `name`：英文，不可重複。
- `crop`：`[x0, y0, x1, y1]`；省略則用整張圖。
- `image`：這格用的圖；省略則用 `source`。
- `narration`：旁白；省略則該格無聲無字幕。引號會影響語音時，字幕另外寫在 `caption`。
- `min`：最短秒數。短旁白給 3.2 秒以上，否則畫得太趕。
- `sfx`：`type` 可用 `pour`（倒水）、`heart`（心跳）、`gulp`（吞嚥）、`wind`（風）、`ding`（叮）。`at` 可用 `start`、`voice`、`voice_end`，另有 `offset`、`dur`、`span`（跨幾格）、`vol`。

字幕每句不超過約 34 字，超過就拆格或拆句，否則會超出畫面。

### 3. 檢查線稿

```bash
python -I <skill>/scripts/draw.py preview
```

讀 `preview.jpg`，確認每格沒切到鄰格、線稿看得出內容，並核對順序和腳本相符。

### 4. 生成旁白與動畫

```bash
powershell -ExecutionPolicy Bypass -File <skill>/scripts/tts.ps1
python -I <skill>/scripts/draw.py
node <skill>/scripts/build.cjs
npx hyperframes check --json
```

`check` 要 0 錯誤。「軌道字幕很多」的提醒可保留。11 格約需 2 分鐘。

### 5. 輸出與檢查

```bash
npx hyperframes render --output out.mp4
```

- 用 ffprobe 確認有音軌、長度正確，用 `volumedetect` 確認音量。
- 用 ffmpeg 抽每格「上色完成後」的畫面，拼成一張來看，再抽幾張畫到一半的。確認完整圖停留夠久，看得清楚。

### 6. 交付

把 `out.mp4` 改成有意義的中文檔名複製到使用者的資料夾，連同 `story.json`、`assets`、`compositions`、`index.html`、`timing.json`、原圖一起放。用 SendUserFile 傳影片。

交付時如實說明：
- 聲音只量過音量，沒有實際聽過；動作只抽格，沒有連續播放看過。
- 腳本要求但沒做到的音效（笑聲、呻吟聲這類合成不自然的，或背景音樂）。
- 圖和腳本不符之處，例如腳本寫捏鼻子，圖上沒有。
- 原圖解析度偏低時畫面會偏柔；每格獨立的高解析圖效果會更好。

## 調整

- **節奏：** 在 `draw.py` 的 `draw_panel` 調 `n_line`、`n_col` 比例。目前勾線 42%、上色 24%，其餘是完成圖的停留時間。
- **線稿太雜或太淡：** 調 `prepare` 的 `adaptiveThreshold` 最後一個參數，越大線越少；`keep` 控制去除的雜點大小。
- **語音：** `tts.ps1 -Voice Zhiwei` 換男聲，`-Rate` 調語速。
- 修改後重跑 `draw.py`、`build.cjs` 和輸出。只改字幕或音效時，不用重跑 `draw.py`。
