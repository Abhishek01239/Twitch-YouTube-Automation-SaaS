import {redirect} from "next/navigation";
import Link from "next/link";
import {createClient} from "@/lib/supabase/server";
import BillingButton from "./BillingButton";

export default async function Dashboard(){
  const supabase=await createClient();
  const {data:{user}}=await supabase.auth.getUser();
  if(!user) redirect("/login");

  const [{data:twitch},{data:channels}]=await Promise.all([
    supabase.from("twitch_connections").select("twitch_login,twitch_display_name").eq("user_id",user.id).maybeSingle(),
    supabase.from("channels").select("id,name,youtube_channel_id,status,subscriptions(status,current_period_end)").eq("user_id",user.id).order("created_at",{ascending:true})
  ]);

  const connected=twitch?.twitch_login;
  const channelCount=channels?.length ?? 0;
  const activeCount=channels?.filter(c=>c.status==="active").length ?? 0;

  return <main className="min-h-screen px-6 py-12">
    <div className="mx-auto max-w-6xl">
      <p className="text-sm text-purple-400">SHORTSFLOW</p>
      <h1 className="mt-2 text-4xl font-bold">Dashboard</h1>
      <p className="mt-2 text-zinc-500">{user.email}</p>

      <div className="mt-10 grid gap-5 md:grid-cols-4">
        {[["Connected channels",String(channelCount)],["Active channels",String(activeCount)],["Shorts today","0 / 3"],["Subscription",channels?.some(c=>c.subscriptions?.[0]?.status==="active")?"Active":"Not active"]].map(([a,b])=>
          <div key={a} className="rounded-2xl border border-zinc-800 bg-zinc-950 p-5">
            <p className="text-sm text-zinc-500">{a}</p>
            <p className="mt-2 text-2xl font-semibold">{b}</p>
          </div>
        )}
      </div>

      <div className="mt-8 grid gap-6 md:grid-cols-2">
        <div className="rounded-2xl border border-zinc-800 bg-zinc-950 p-8">
          <h2 className="text-2xl font-semibold">Twitch source</h2>
          <p className="mt-2 text-zinc-400">
            {connected ? `Connected as @${twitch.twitch_login}.` : "Connect your Twitch account so the automation can use your authorized Twitch data."}
          </p>
          <Link href="/api/twitch/connect" className="mt-6 inline-block rounded-xl bg-white px-6 py-3 font-semibold text-black">
            {connected ? "Reconnect Twitch" : "Connect Twitch"}
          </Link>
        </div>

        <div className="rounded-2xl border border-zinc-800 bg-zinc-950 p-8">
          <h2 className="text-2xl font-semibold">YouTube channels</h2>
          <p className="mt-2 text-zinc-400">Connect one or more YouTube channels. Each connected channel can later be activated with the ₹99/month subscription.</p>
          <Link href="/api/youtube/connect" className="mt-6 inline-block rounded-xl bg-white px-6 py-3 font-semibold text-black">
            Connect YouTube channel
          </Link>
          {channelCount>0 && <div className="mt-6 space-y-3">
            {channels!.map(channel=><div key={channel.id} className="rounded-xl border border-zinc-800 p-4">
              <p className="font-medium">{channel.name}</p>
              <p className="text-sm text-zinc-500">{channel.youtube_channel_id}</p>
              <p className="mt-1 text-xs uppercase tracking-wide text-zinc-500">{channel.status}</p>{channel.subscriptions?.[0]?.status==="active" ? <p className="mt-2 text-xs text-emerald-400">Subscription active</p> : <BillingButton channelId={channel.id}/>}
            </div>)}
          </div>}
        </div>
      </div>
    </div>
  </main>;
}