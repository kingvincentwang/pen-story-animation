// Assembles the HyperFrames project from story.json + timing.json: video, captions, voice, sound.
// Run from the project folder after draw.py: node <skill>/scripts/build.cjs
const fs = require('fs');
const { execFileSync } = require('child_process');
const story = JSON.parse(fs.readFileSync('story.json', 'utf8'));
const T = JSON.parse(fs.readFileSync('timing.json', 'utf8'));
const LEAD = 0.45;
const TAIL = story.tail ?? 2.2;
const last = T[T.length - 1];
const TOTAL = +(last.start + last.dur).toFixed(3);

// ---------- sound presets, synthesised so nothing needs downloading ----------
const noise = (d, seed) => `anoisesrc=d=${d}:c=pink:r=44100:a=0.7:s=${seed}`;
const PRESET = {
  pour: (d) => [noise(d, 3), `highpass=f=800,lowpass=f=4500,tremolo=f=7:d=0.5,afade=t=in:d=0.25,afade=t=out:st=${Math.max(0, d - 0.5)}:d=0.5`],
  heart: (d) => [`aevalsrc='0.9*sin(2*PI*58*t)*exp(-13*mod(t,0.72))+0.7*sin(2*PI*50*t)*exp(-13*mod(t-0.22,0.72))*gte(mod(t,0.72),0.22)':d=${d}:s=44100`, `afade=t=out:st=${Math.max(0, d - 0.5)}:d=0.5`],
  gulp: (d) => [`aevalsrc='0.8*sin(2*PI*(170+500*mod(t,0.5))*t)*exp(-9*mod(t,0.5))':d=${d}:s=44100`, null],
  wind: (d) => [noise(d, 5), `bandpass=f=420:w=300,tremolo=f=0.35:d=0.7,afade=t=in:d=1,afade=t=out:st=${Math.max(0, d - 1)}:d=1`],
  ding: (d) => [`aevalsrc='(0.7*sin(2*PI*1320*t)+0.3*sin(2*PI*2640*t))*exp(-3.5*t)':d=${d}:s=44100`, null],
};
const DEFAULT_LEN = { pour: 2.6, gulp: 1, ding: 1.5 };
const DEFAULT_VOL = { pour: 0.3, heart: 0.9, gulp: 0.5, wind: 0.45, ding: 0.6 };
fs.mkdirSync('assets/sfx', { recursive: true });
const sfxTags = [];
story.panels.forEach((p, i) => {
  (p.sfx || []).forEach((s, k) => {
    const t = T[i], make = PRESET[s.type];
    if (!make) throw new Error(`unknown sfx type "${s.type}" on panel ${p.name}`);
    const span = T.slice(i, i + (s.span || 1)).reduce((a, x) => a + x.dur, 0);
    const d = +(s.dur ?? DEFAULT_LEN[s.type] ?? span).toFixed(3);
    const base = s.at === 'voice_end' ? t.start + LEAD + t.voice_len : s.at === 'voice' ? t.start + LEAD : t.start;
    const st = +(base + (s.offset || 0)).toFixed(3);
    const id = `sfx-${p.name}-${k}`, [src, af] = make(d);
    execFileSync('ffmpeg', ['-y', '-v', 'error', '-f', 'lavfi', '-i', src, ...(af ? ['-af', af] : []), '-ac', '1', `assets/sfx/${id}.wav`]);
    sfxTags.push(`<audio id="${id}" class="clip" src="assets/sfx/${id}.wav" data-start="${st}" data-duration="${d}" data-track-index="${21 + sfxTags.length}" data-volume="${s.vol ?? DEFAULT_VOL[s.type]}"></audio>`);
  });
});

// pen scratch only while a panel is being drawn or coloured
const gate = T.map((t, i) => {
  const s = i ? 0.4 : 0, hold = i === T.length - 1 ? TAIL : 0;
  return `between(t,${(t.start + s).toFixed(2)},${(t.start + s + (t.dur - s - hold) * 0.66).toFixed(2)})`;
}).join('+');
fs.writeFileSync('assets/pen-filter.txt', `highpass=f=1800,lowpass=f=7000,tremolo=f=11:d=0.7,volume='if(${gate},1,0)':eval=frame`);
execFileSync('ffmpeg', ['-y', '-v', 'error', '-f', 'lavfi', '-i', `anoisesrc=d=${TOTAL}:c=pink:r=44100:a=0.6:s=7`, '-filter_script:a', 'assets/pen-filter.txt', '-ac', '1', 'assets/pen.wav']);

// ---------- captions ----------
const caps = T.filter((t) => t.caption && t.voice).map((t) => `<div id="cap-${t.name}" class="clip cap" data-start="${(t.start + LEAD).toFixed(3)}" data-duration="${(t.voice_len + 0.2).toFixed(3)}" data-track-index="9"><span>${t.caption}</span></div>`).join('\n    ');
fs.mkdirSync('compositions', { recursive: true });
fs.writeFileSync('compositions/caps.html', `<template>
  <style>
    @font-face { font-family: 'JhengHei Local'; src: local('Microsoft JhengHei Bold'), local('Microsoft JhengHei'); }
    #root { position: absolute; inset: 0; }
    .cap { position: absolute; left: 0; right: 0; top: 925px; text-align: center; font: 700 46px 'JhengHei Local', sans-serif; color: #fff; }
    .cap span { display: inline-block; padding: 12px 34px; border-radius: 14px; background: rgba(30, 28, 38, 0.9); }
  </style>
  <div id="root" data-composition-id="caps" data-width="1920" data-height="1080">
    ${caps}
  </div>
  <script>window.__timelines['caps'] = gsap.timeline({ paused: true });</script>
</template>
`);

// ---------- root ----------
const voice = T.filter((t) => t.voice).map((t) => `<audio id="voice-${t.name}" class="clip" src="assets/voice/${t.name}.wav" data-start="${(t.start + LEAD).toFixed(3)}" data-duration="${t.voice_len}" data-track-index="20" data-volume="1"></audio>`).join('\n      ');
fs.writeFileSync('index.html', `<!doctype html>
<html lang="zh-Hant">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      * { margin: 0; padding: 0; box-sizing: border-box; }
      html, body { margin: 0; width: 1920px; height: 1080px; overflow: hidden; background: #fbf7ec; }
      #root { position: relative; width: 100%; height: 100%; background: #fbf7ec; }
      #story { position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; z-index: 1; }
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="${TOTAL}" data-width="1920" data-height="1080">
      <video id="story" class="clip" src="assets/story.mp4" muted playsinline data-start="0" data-duration="${TOTAL}" data-track-index="1"></video>
      <div id="caps" data-composition-id="caps" data-composition-src="compositions/caps.html" data-start="0" data-duration="${TOTAL}" data-track-index="9" data-track-kind="captions" data-width="1920" data-height="1080" style="z-index:9"></div>
      ${voice}
      ${sfxTags.join('\n      ')}
      <audio id="pen" class="clip" src="assets/pen.wav" data-start="0" data-duration="${TOTAL}" data-track-index="60" data-volume="0.12"></audio>
    </div>
    <script>
      window.__timelines = window.__timelines || {};
      window.__timelines["main"] = gsap.timeline({ paused: true });
    </script>
  </body>
</html>
`);
console.log('total', TOTAL);
