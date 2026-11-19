import fs from 'node:fs/promises';
import { createWriteStream } from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { pipeline } from 'node:stream/promises';
import ffmpegPath from 'ffmpeg-static';
import { Ytdl } from '@distube/ytdl-core';
import { parseVtt, selectHighlights, srtForWindow } from './lib.js';

const dataRoot = path.resolve('data');
const yt = new Ytdl({
  country: 'IN',
  lang: 'hi',
  timeoutMs: 45000,
  cookie: process.env.YOUTUBE_COOKIE || undefined
});

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
  const info = await yt.getInfo(job.url);
  const details = info.videoDetails;
  const duration = Number(details.lengthSeconds || 0);
  const maxSeconds = Number(process.env.MAX_VIDEO_MINUTES || 90) * 60;
  if (!duration || duration > maxSeconds) throw new Error(`वीडियो ${process.env.MAX_VIDEO_MINUTES || 90} मिनट से कम होना चाहिए।`);

  update({ title: details.title, thumbnail: details.thumbnails?.at(-1)?.url, duration, stage: 'वीडियो डाउनलोड हो रहा है', progress: 15 });
  const videoFormats = info.formats.filter(f => f.hasVideo && Number(f.height || 0) <= 720)
    .sort((a, b) => Number(b.height || 0) - Number(a.height || 0) || Number(b.bitrate || 0) - Number(a.bitrate || 0));
  const videoFormat = videoFormats.find(f => !f.hasAudio) || videoFormats[0];
  if (!videoFormat) throw new Error('वीडियो stream उपलब्ध नहीं है।');
  const videoFile = path.join(dir, `video.${videoFormat.container || 'mp4'}`);
  const downloads = [pipeline(yt.download(info, { format: videoFormat }), createWriteStream(videoFile))];
  let audioFile = null;
  if (!videoFormat.hasAudio) {
    const audioFormat = info.formats.filter(f => f.hasAudio && !f.hasVideo)
      .sort((a, b) => Number(b.audioBitrate || 0) - Number(a.audioBitrate || 0))[0];
    if (!audioFormat) throw new Error('ऑडियो stream उपलब्ध नहीं है।');
    audioFile = path.join(dir, `audio.${audioFormat.container || 'webm'}`);
    downloads.push(pipeline(yt.download(info, { format: audioFormat }), createWriteStream(audioFile)));
  }
  await Promise.all(downloads);
  const source = path.join(dir, 'source.mp4');
  const mergeArgs = audioFile
    ? ['-y', '-i', videoFile, '-i', audioFile, '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-movflags', '+faststart', source]
    : ['-y', '-i', videoFile, '-map', '0:v:0', '-map', '0:a?', '-c:v', 'copy', '-c:a', 'aac', '-movflags', '+faststart', source];
  await command(ffmpegPath, mergeArgs, log);
  await Promise.all([fs.rm(videoFile, { force: true }), audioFile ? fs.rm(audioFile, { force: true }) : null]);

  update({ stage: 'कैप्शन तैयार हो रहे हैं', progress: 32 });
  let cues = [];
  try {
    const tracks = info.captionTracks || [];
    const track = tracks.find(t => /^hi\b/i.test(t.languageCode)) || tracks.find(t => /^en\b/i.test(t.languageCode)) || tracks[0];
    if (track) cues = parseVtt(await yt.getCaptions(info, { lang: track.languageCode }));
  } catch (error) { log(error.message); }
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
    const filters = [
      '[0:v]split=2[base][front]',
      '[base]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=28[bg]',
      '[front]scale=1000:1540:force_original_aspect_ratio=decrease[fg]',
      '[bg][fg]overlay=(W-w)/2:(H-h)/2,drawbox=x=0:y=0:w=iw:h=250:color=black@0.58:t=fill',
      `subtitles='${hookEscaped}'`
    ];
    if (cues.length) filters.push(`subtitles='${srtEscaped}':force_style='FontName=Sans,FontSize=17,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3,Outline=3,Shadow=1,BackColour=&H9A000000,Alignment=2,MarginV=120'`);
    filters.push('fade=t=in:st=0:duration=0.25,fade=t=out:st=' + Math.max(0, job.clipLength - .35) + ':duration=0.35[v]');
    const filter = filters.join(',');
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
