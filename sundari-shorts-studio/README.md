# Sundari Shorts Studio

Self-hosted YouTube-to-Shorts web app. It downloads an authorized public YouTube video, finds useful transcript windows, renders vertical 1080×1920 clips, adds a top hook and bottom captions, normalizes audio, and exposes a small REST API.

## Run

```bash
npm install
npm start
```

Open `http://localhost:3000`. Node 20+ is required. Generated media is deleted after 12 hours by default.

## API

`POST /api/jobs`

```json
{
  "url": "https://youtube.com/watch?v=...",
  "hook": "आखिर तक ज़रूर देखें",
  "count": 3,
  "clipLength": 45,
  "rightsConfirmed": true
}
```

Poll `GET /api/jobs/:id` until `status` is `completed` or `failed`.

## Notes

- Use only videos you own or have permission to download and edit.
- YouTube may block datacenter IPs or require login. For an authorized account, set `YOUTUBE_COOKIE` to a Netscape-format cookie export in the hosting environment. Treat it like a password and never commit it.
- The app intentionally does not bypass login, private-video access, age gates, or other access controls.
- Hostinger needs enough CPU/RAM and permission to execute the bundled FFmpeg/yt-dlp binaries.
