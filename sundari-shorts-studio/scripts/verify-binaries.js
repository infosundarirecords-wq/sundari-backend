import ffmpegPath from 'ffmpeg-static';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

if (!ffmpegPath) throw new Error('FFmpeg binary was not installed');
const here = path.dirname(fileURLToPath(import.meta.url));
const ytDlpPath = path.resolve(here, '../node_modules/youtube-dl-exec/bin', process.platform === 'win32' ? 'yt-dlp.exe' : 'yt-dlp');
await Promise.all([fs.access(ffmpegPath), fs.access(ytDlpPath)]);
console.log('Video engine ready');
