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
3. **Your own gameplay**: upload a recording on the dashboard. The worker measures per-second audio
   loudness, picks the most intense non-overlapping windows, and cuts them into captioned 9:16 Shorts.

Run migration `009_approved_streamers_and_gameplay.sql`, then reconnect Twitch so the token has the
`editor:manage:clips` scope.
