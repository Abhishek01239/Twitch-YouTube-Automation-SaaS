import {redirect} from "next/navigation";
import Link from "next/link";
import {createClient} from "@/lib/supabase/server";

export default async function Dashboard(){
  const supabase=await createClient();
  const {data:{user}}=await supabase.auth.getUser();
  if(!user) redirect("/login");

  const {data:twitch}=await supabase
    .from("twitch_connections")
    .select("twitch_login,twitch_display_name")
    .eq("user_id",user.id)
    .maybeSingle();

  const connected=twitch?.twitch_login;
  return <main className="min-h-screen px-6 py-12">
    <div className="mx-auto max-w-6xl">
      <p className="text-sm text-purple-400">SHORTSFLOW</p>
      <h1 className="mt-2 text-4xl font-bold">Dashboard</h1>
      <p className="mt-2 text-zinc-500">{user.email}</p>

      <div className="mt-10 grid gap-5 md:grid-cols-4">
        {[["Active channels","0"],["Shorts today","0 / 3"],["Next distribution","—"],["Subscription","Not active"]].map(([a,b])=>
          <div key={a} className="rounded-2xl border border-zinc-800 bg-zinc-950 p-5">
            <p className="text-sm text-zinc-500">{a}</p>
            <p className="mt-2 text-2xl font-semibold">{b}</p>
          </div>
        )}
      </div>

      <div className="mt-8 rounded-2xl border border-zinc-800 bg-zinc-950 p-8">
        <h2 className="text-2xl font-semibold">Connect Twitch</h2>
        <p className="mt-2 text-zinc-400">
          {connected ? `Connected as @${twitch.twitch_login}.` : "Connect your Twitch account so the automation can use your authorized Twitch data."}
        </p>
        <Link href="/api/twitch/connect" className="mt-6 inline-block rounded-xl bg-white px-6 py-3 font-semibold text-black">
          {connected ? "Reconnect Twitch" : "Connect Twitch"}
        </Link>
      </div>

      <div className="mt-6 rounded-2xl border border-zinc-800 bg-zinc-950 p-8">
        <h2 className="text-2xl font-semibold">YouTube</h2>
        <p className="mt-2 text-zinc-400">Next we will connect your YouTube channel and then activate it after the ₹99 subscription.</p>
      </div>
    </div>
  </main>;
}