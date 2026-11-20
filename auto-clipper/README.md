# Auto Clipper

Runs on **GitHub Actions** every 6 hours:

1. **Finds sources:** top Twitch clips, recent Twitch VODs, and/or YouTube videos (set in `config.yaml`).
2. **Finds highlights:** Twitch clips are already highlights. For long VODs and videos it scans audio loudness and picks the hype peaks.
3. **Renders Shorts:** 1080×1920, gameplay centred on a blurred background (or a centre crop), with word-by-word pop-up captions from Whisper, which runs locally (no API key needed).
4. **Posts via Zernio:** uploads each Short and schedules it with a gap between posts (default 2 h). The gap is kept across runs.
5. **Remembers what it posted:** saves `state/state.json` back to the repo so nothing is posted twice.

> Only clip channels you own or have permission to repost. Every post includes a credit line linking the source.

## Setup

1. **Repository secrets** (Settings → Secrets and variables → Actions → Secrets):
   | Secret | Needed for |
   |---|---|
   | `ZERNIO_API_KEY` | posting (zernio.com → API keys) |
   | `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET` | Twitch sources (already used by the main worker) |
   | `YTDLP_COOKIES` | optional: YouTube sources. Paste a Netscape `cookies.txt` export. YouTube blocks downloads from GitHub's servers without it. |
2. **Edit `config.yaml`:** add your Twitch login(s) under `sources.twitch_clips.channels` (and/or `twitch_vods`, `youtube`).

### Which Zernio account posts
Posting uses only the Zernio account that owns the `ZERNIO_API_KEY` secret. To post from a different Zernio account:
1. Sign up for or log in to the other Zernio account, connect the YouTube channel there, and create an API key.
2. Save that key as the `ZERNIO_API_KEY` repository secret.
3. Run the workflow with **list_accounts** ticked. The log shows that key's channels and their `account_id`s.
4. In `config.yaml`, set `posting.accounts[].username` (or `account_id`) to the channel to post to.

`posting.blocked_account_ids` lists accounts that must never be posted to. The run stops with an error if a post would target one. The original account `galaxyofgamesar07` is blocked by default.
3. **Test:** Actions → *Auto Clipper* → *Run workflow*, with **Dry run** ticked. Download the `clips-…` artifact and watch the clips.
4. **Go live:**
   - Manual runs: untick *Dry run*.
   - Scheduled runs: add the repository **variable** `AUTO_CLIPPER_LIVE` = `true` (Settings → Variables). Until then, scheduled runs only render clips and post nothing.

GitHub only runs scheduled workflows, and only shows the *Run workflow* button, from the **default branch**. Merge this into `main` first.

## Run locally

```bash
cd auto-clipper
pip install -r requirements.txt          # needs ffmpeg on PATH
python -m clipper.main --file my_vod.mp4 --dry-run        # local file
python -m clipper.main --url https://www.twitch.tv/videos/123 --dry-run
ZERNIO_API_KEY=... python -m clipper.main                 # configured sources, live
```

## Tuning (`config.yaml`)

- `clips.length` / `lead_in`: clip length and seconds kept before the peak.
- `clips.min_score`: lower it to get more highlights from long VODs, raise it to get fewer.
- `clips.layout`: `fit` (blurred background) or `fill` (centre crop, good for full-screen gameplay).
- `clips.whisper_model`: `tiny`, `base` or `small`. `language`: `auto`, `en`, `hi`, …
- `posting.max_posts_per_run`, `gap_minutes`, `youtube.visibility`, title and description templates.
- Add more Zernio accounts (for example Instagram or TikTok) under `posting.accounts`.
