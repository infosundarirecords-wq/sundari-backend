import express from 'express';
import helmet from 'helmet';
import { nanoid } from 'nanoid';
import path from 'node:path';
import { isYouTubeUrl } from './lib.js';
import { cleanupOldJobs, processJob } from './processor.js';

const app = express();
const port = Number(process.env.PORT || 3000);
const jobs = new Map();
const queue = [];
let running = 0;
const maxConcurrent = Number(process.env.MAX_CONCURRENT_JOBS || 1);

app.use(helmet({ contentSecurityPolicy: false, crossOriginResourcePolicy: false }));
app.use(express.json({ limit: '32kb' }));
app.use('/media', express.static(path.resolve('data'), { maxAge: '1h', fallthrough: false }));
app.use(express.static(path.resolve('public')));

app.get('/api/health', (_req, res) => res.json({ ok: true, service: 'Sundari Shorts Studio', queue: queue.length, running }));
app.post('/api/jobs', (req, res) => {
  const { url, hook = '', rightsConfirmed } = req.body || {};
  const count = Math.max(1, Math.min(6, Number(req.body?.count || 3)));
  const clipLength = [30, 45, 60].includes(Number(req.body?.clipLength)) ? Number(req.body.clipLength) : 45;
  if (!isYouTubeUrl(url)) return res.status(400).json({ error: 'सही YouTube लिंक डालें।' });
  if (!rightsConfirmed) return res.status(400).json({ error: 'पहले वीडियो के उपयोग अधिकार की पुष्टि करें।' });
  const job = { id: nanoid(12), url, hook: String(hook).slice(0, 80), count, clipLength, status: 'queued', stage: 'कतार में', progress: 1, createdAt: new Date().toISOString(), outputs: [] };
  jobs.set(job.id, job); queue.push(job); runQueue();
  res.status(202).json({ id: job.id, statusUrl: `/api/jobs/${job.id}` });
});
app.get('/api/jobs/:id', (req, res) => {
  const job = jobs.get(req.params.id);
  if (!job) return res.status(404).json({ error: 'यह जॉब नहीं मिला या expire हो गया।' });
  res.json(job);
});
app.get('/{*splat}', (_req, res) => res.sendFile(path.resolve('public/index.html')));

async function runQueue() {
  if (running >= maxConcurrent || !queue.length) return;
  const job = queue.shift(); running++; job.status = 'processing';
  try {
    job.outputs = await processJob(job, patch => Object.assign(job, patch));
    Object.assign(job, { status: 'completed', stage: 'शॉर्ट्स तैयार हैं', progress: 100, completedAt: new Date().toISOString() });
  } catch (error) {
    console.error(error); Object.assign(job, { status: 'failed', stage: 'प्रोसेसिंग रुकी', error: friendlyError(error), progress: 100 });
  } finally { running--; runQueue(); }
}

function friendlyError(error) {
  const msg = String(error?.message || error);
  if (/Sign in|confirm you’re not a bot|cookies/i.test(msg)) return 'YouTube ने इस वीडियो के लिए लॉगिन माँगा। कोई दूसरा public वीडियो आज़माएँ।';
  if (/copyright|unavailable|private/i.test(msg)) return 'वीडियो private, unavailable या सीमित है।';
  return msg.slice(-500);
}

cleanupOldJobs(Number(process.env.JOB_RETENTION_HOURS || 12)).catch(console.error);
setInterval(() => cleanupOldJobs(Number(process.env.JOB_RETENTION_HOURS || 12)).catch(console.error), 3600000).unref();
app.listen(port, () => console.log(`Sundari Shorts Studio listening on ${port}`));
