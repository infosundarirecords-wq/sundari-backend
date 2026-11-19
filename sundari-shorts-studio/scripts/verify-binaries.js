import ffmpegPath from 'ffmpeg-static';
import fs from 'node:fs/promises';

if (!ffmpegPath) throw new Error('FFmpeg binary was not installed');
await fs.access(ffmpegPath);
console.log('Video engine ready');
