import fs from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';
import ffmpegPath from 'ffmpeg-static';
import youtubedl from 'youtube-dl-exec';
import { findFirst, parseVtt, selectHighlights, srtForWindow } from './lib.js';

const dataRoot = path.resolve('data');
const ffprobePath = ffmpegPath.replace(/ffmpeg(?:\.exe)?$/, process.platform === 'win32' ? 'ffprobe.exe' : 'ffprobe');

async function command(bin, args, onLog = () => {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(bin, args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let output = '';
    child.stdout.on('data', b => { output += b; onLog(b.toString()); });
    child.stderr.on('data', b => { output += b; onLog(b.toString()); });
    child.on('error', reject);
    child.on('close', code => code === 0 ? resolve(output) : reject(new Error(output.slice(-3000))));
  });
}

export async function processJob(job, update) {
  const dir = path.join(dataRoot, job.id);
  await fs.mkdir(dir, { recursive: true });
  const log = text => update({ log: String(text).slice(-1200) });
  update({ stage: 'वीडियो की जानकारी पढ़ी जा रही है', progress: 8 });
  const info = await youtubedl(job.url, { dumpSingleJson: true, noPlaylist: true, noWarnings: true });
  const duration = Number(info.duration || 0);
  const maxSeconds = Number(process.env.MAX_VIDEO_MINUTES || 90) * 60;
  if (!duration || duration > maxSeconds) throw new Error(`वीडियो ${process.env.MAX_VIDEO_MINUTES || 90} मिनट से कम होना चाहिए।`);

  update({ title: info.title, thumbnail: info.thumbnail, duration, stage: 'वीडियो डाउनलोड हो रहा है', progress: 15 });
  await youtubedl(job.url, {
    noPlaylist: true,
    format: 'bv*[height<=720]+ba/b[height<=720]',
    mergeOutputFormat: 'mp4',
    output: path.join(dir, 'source.%(ext)s'),
    noWarnings: true
  });
  const source = await findFirst(dir, /^source\.(mp4|mkv|webm|mov)$/i);
  if (!source) throw new Error('वीडियो डाउनलोड नहीं हो पाया।');

  update({ stage: 'कैप्शन तैयार हो रहे हैं', progress: 32 });
  try {
    await youtubedl(job.url, {
      noPlaylist: true, skipDownload: true, writeAutoSubs: true, writeSubs: true,
      subLangs: 'hi.*,en.*', subFormat: 'vtt', output: path.join(dir, 'caption.%(ext)s'), noWarnings: true
    });
  } catch (error) { log(error.message); }
  const vttPath = await findFirst(dir, /^caption\..*\.vtt$/i);
  const cues = vttPath ? parseVtt(await fs.readFile(vttPath, 'utf8')) : [];
  const picks = selectHighlights(cues, duration, job.count, job.clipLength);
  const outputs = [];

  for (let i = 0; i < picks.length; i++) {
    const pick = picks[i];
    const srt = path.join(dir, `clip-${i + 1}.srt`);
    await fs.writeFile(srt, srtForWindow(cues, pick.start, job.clipLength));
    const hookFile = path.join(dir, `hook-${i + 1}.ass`);
    await fs.writeFile(hookFile, makeHookAss(job.hook || 'SUNDARI SHORTS', job.clipLength));
    const output = path.join(dir, `short-${i + 1}.mp4`);
    update({ stage: `शॉर्ट ${i + 1}/${picks.length} एडिट हो रहा है`, progress: 38 + Math.round(i / picks.length * 55) });
    const srtEscaped = srt.replace(/'/g, "'\\''").replace(/:/g, '\\:');
    const hookEscaped = hookFile.replace(/'/g, "'\\''").replace(/:/g, '\\:');
    const filter = [
      '[0:v]split=2[base][front]',
      '[base]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=28[bg]',
      '[front]scale=1000:1540:force_original_aspect_ratio=decrease[fg]',
      '[bg][fg]overlay=(W-w)/2:(H-h)/2,drawbox=x=0:y=0:w=iw:h=250:color=black@0.58:t=fill',
      `subtitles='${hookEscaped}'`,
      `subtitles='${srtEscaped}':force_style='FontName=Sans,FontSize=17,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3,Outline=3,Shadow=1,BackColour=&H9A000000,Alignment=2,MarginV=120'`,
      'fade=t=in:st=0:duration=0.25,fade=t=out:st=' + Math.max(0, job.clipLength - .35) + ':duration=0.35[v]'
    ].join(',');
    await command(ffmpegPath, ['-y', '-ss', String(pick.start), '-i', source, '-t', String(job.clipLength),
      '-filter_complex', filter, '-map', '[v]', '-map', '0:a?', '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=in:duration=0.2,afade=t=out:st=' + Math.max(0, job.clipLength - .3) + ':duration=0.3',
      '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', output], log);
    outputs.push({ name: `Short ${i + 1}`, url: `/media/${job.id}/short-${i + 1}.mp4`, start: Math.round(pick.start) });
  }
  await fs.rm(source, { force: true });
  return outputs;
}

function makeHookAss(text, duration) {
  const safe = String(text).replace(/[{}]/g, '').replace(/\r?\n/g, ' ').slice(0, 80);
  const end = `0:${String(Math.floor(duration / 60)).padStart(2, '0')}:${String(duration % 60).padStart(2, '0')}.00`;
  return `[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Hook,Sans,62,&H00FFFFFF,&H000000FF,&H00000000,&H88000000,-1,0,0,0,100,100,0,0,3,3,1,8,60,60,70,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:00.00,${end},Hook,,0,0,0,,{\\an8\\pos(540,80)}${safe}\n`;
}

export async function cleanupOldJobs(hours = 12) {
  await fs.mkdir(dataRoot, { recursive: true });
  const now = Date.now();
  for (const name of await fs.readdir(dataRoot)) {
    const dir = path.join(dataRoot, name);
    const stat = await fs.stat(dir).catch(() => null);
    if (stat?.isDirectory() && now - stat.mtimeMs > hours * 3600000) await fs.rm(dir, { recursive: true, force: true });
  }
}
