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