# Twitch → YouTube Automation SaaS

Product rules:
- ₹99/month per channel
- 3 source Shorts per day
- Minimum 2-hour gap between distributions on each channel
- Same source Shorts can be distributed to every active subscribed channel
- YouTube OAuth is per channel
- Subscription and scheduling rules are enforced server-side

Stack: Next.js, Supabase, Razorpay, Twitch, YouTube Data API, GitHub Actions.

Secrets stay in GitHub Actions/Vercel environment variables.

Next implementation: Supabase auth, Twitch OAuth, YouTube OAuth, Razorpay webhooks, source video processing, and production upload worker.
## Content sources

All sources are permission-based so channels don't collect copyright strikes.

1. **Your own Twitch clips**: top clips from the connected Twitch account.
2. **Approved streamers**: add a streamer on the dashboard with a note of how they gave permission
   (optionally limited to one game, e.g. `Grand Theft Auto VI`). The streamer must add your Twitch
   account as a **channel editor** (Creator Dashboard → Settings → Roles Manager); Twitch's clip
   download API refuses otherwise. These Shorts get a `twitch.tv/<streamer>` credit overlay and are
   only distributed to the approving user's own channels.
3. **Your own gameplay**: upload a recording on the dashboard (gameplay or a downloaded VOD of your
   own stream) and the worker picks the best moments for you (`lib/highlights.ts`):
   - **Audio spikes**: moments far louder than the surrounding minute (gunfire, crashes, yelling),
     so a constantly loud game doesn't hide the real peaks.
   - **On-screen action**: frame-to-frame pixel change (chases, explosions, fast camera).
   - **Hype speech**: Whisper transcript scanned for "oh my god", "let's go", "clip that", laughing, fast talking.
   - **Clean cuts**: the peak lands ~60% into the clip (build-up + payoff) and cuts snap to sentence boundaries.
   - **AI judge**: the top candidates' transcripts go to a Groq LLM (`GROQ_LLM_MODEL`, default
     `llama-3.3-70b-versatile`) which picks the best and writes titles. Falls back to signal ranking.

   Run `npm test` for the highlight-detection tests.

Run migration `009_approved_streamers_and_gameplay.sql`, then reconnect Twitch so the token has the
`editor:manage:clips` scope.
