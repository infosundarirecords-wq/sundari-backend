import fs from 'node:fs/promises';

export function isYouTubeUrl(value) {
  try {
    const url = new URL(value);
    return ['youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'].includes(url.hostname);
  } catch { return false; }
}

export function parseVtt(input) {
  const cues = [];
  const blocks = input.replace(/\r/g, '').split(/\n\n+/);
  for (const block of blocks) {
    const lines = block.split('\n').filter(Boolean);
    const timeLine = lines.findIndex(line => line.includes('-->'));
    if (timeLine < 0) continue;
    const [a, b] = lines[timeLine].split('-->').map(s => s.trim().split(' ')[0]);
    const text = lines.slice(timeLine + 1).join(' ')
      .replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&')
      .replace(/\s+/g, ' ').trim();
    if (!text) continue;
    cues.push({ start: toSeconds(a), end: toSeconds(b), text });
  }
  return cues.filter((cue, i) => !i || cue.text !== cues[i - 1].text);
}

function toSeconds(value) {
  const parts = value.replace(',', '.').split(':').map(Number);
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  return parts[0] * 60 + parts[1];
}

export function selectHighlights(cues, duration, count, clipLength) {
  if (!cues.length) {
    const gap = Math.max(clipLength, duration / (count + 1));
    return Array.from({ length: count }, (_, i) => ({
      start: Math.max(0, Math.min(duration - clipLength, gap * (i + 1) - clipLength / 2)),
      score: 0
    }));
  }
  const hook = /\?|!|कैसे|क्यों|सच|गलती|राज़|देखिए|जानिए|important|secret|how|why|never|best/i;
  const candidates = cues.map((cue, index) => {
    const start = Math.max(0, cue.start - 2);
    const window = cues.filter(x => x.start >= start && x.start < start + clipLength);
    const words = window.reduce((n, x) => n + x.text.split(/\s+/).length, 0);
    const score = words + (hook.test(cue.text) ? 35 : 0) + (cue.text.length < 90 ? 8 : 0);
    return { start, score, index };
  }).sort((a, b) => b.score - a.score);
  const chosen = [];
  for (const item of candidates) {
    const start = Math.min(item.start, Math.max(0, duration - clipLength));
    if (chosen.every(x => Math.abs(x.start - start) > clipLength * .75)) chosen.push({ ...item, start });
    if (chosen.length === count) break;
  }
  return chosen.sort((a, b) => a.start - b.start);
}

export function srtForWindow(cues, start, length) {
  const selected = cues.filter(c => c.end > start && c.start < start + length);
  return selected.map((cue, i) => {
    const a = Math.max(0, cue.start - start);
    const b = Math.min(length, cue.end - start);
    return `${i + 1}\n${srtTime(a)} --> ${srtTime(b)}\n${wrap(cue.text)}\n`;
  }).join('\n');
}

function srtTime(sec) {
  const ms = Math.max(0, Math.round(sec * 1000));
  const h = Math.floor(ms / 3600000);
  const m = Math.floor(ms % 3600000 / 60000);
  const s = Math.floor(ms % 60000 / 1000);
  return [h, m, s].map(v => String(v).padStart(2, '0')).join(':') + ',' + String(ms % 1000).padStart(3, '0');
}

function wrap(text) {
  const words = text.split(/\s+/); let line = ''; const out = [];
  for (const word of words) {
    if ((line + ' ' + word).trim().length > 30) { out.push(line); line = word; }
    else line = (line + ' ' + word).trim();
  }
  if (line) out.push(line);
  return out.slice(0, 3).join('\n');
}

export async function findFirst(dir, pattern) {
  const names = await fs.readdir(dir);
  const name = names.find(n => pattern.test(n));
  return name ? `${dir}/${name}` : null;
}
