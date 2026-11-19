"use client";
import {useActionState} from "react";
import {addApprovedStreamer,type ActionState} from "./actions";

const input="mt-1 w-full rounded-xl border border-zinc-800 bg-black px-4 py-2 text-white";

export default function ApprovedStreamerForm(){
  const [state,action,pending]=useActionState<ActionState,FormData>(addApprovedStreamer,{});
  return <form action={action} className="mt-6 space-y-4">
    <label className="block text-sm text-zinc-400">Twitch username
      <input name="login" required placeholder="streamer_name" className={input}/>
    </label>
    <label className="block text-sm text-zinc-400">How did they give permission?
      <input name="permission" required placeholder="Link to their Discord/Twitter message, email date…" className={input}/>
    </label>
    <label className="block text-sm text-zinc-400">Only clips from this game (optional)
      <input name="game" placeholder="Grand Theft Auto VI" className={input}/>
    </label>
    <label className="flex items-start gap-2 text-sm text-zinc-400">
      <input type="checkbox" name="confirm" className="mt-1"/>
      This streamer has allowed me to clip and post their streams, and has added my Twitch account as a channel editor.
    </label>
    <button disabled={pending} className="rounded-xl bg-white px-6 py-3 font-semibold text-black disabled:opacity-50">{pending?"Adding…":"Add streamer"}</button>
    {state.error&&<p className="text-sm text-red-400">{state.error}</p>}
    {state.ok&&<p className="text-sm text-emerald-400">{state.ok}</p>}
  </form>;
}
