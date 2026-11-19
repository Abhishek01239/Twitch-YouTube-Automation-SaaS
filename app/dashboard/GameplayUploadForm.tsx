"use client";
import {useState} from "react";
import {useRouter} from "next/navigation";
import {createClient} from "../../lib/supabase/client";

const input="mt-1 w-full rounded-xl border border-zinc-800 bg-black px-4 py-2 text-white";

export default function GameplayUploadForm({userId}:{userId:string}){
  const router=useRouter();
  const [status,setStatus]=useState<{error?:string;ok?:string}>({});
  const [busy,setBusy]=useState(false);

  async function submit(event:React.FormEvent<HTMLFormElement>){
    event.preventDefault();
    const form=new FormData(event.currentTarget);
    const file=form.get("file") as File|null;
    if(!file||!file.size){setStatus({error:"Choose a recording to upload."});return;}
    setBusy(true);setStatus({});
    try{
      const supabase=createClient();
      const ext=(file.name.split(".").pop()||"mp4").toLowerCase().replace(/[^a-z0-9]/g,"");
      const storagePath=`${userId}/${crypto.randomUUID()}.${ext}`;
      const {error:uploadError}=await supabase.storage.from("gameplay-uploads").upload(storagePath,file,{contentType:file.type||"video/mp4"});
      if(uploadError)throw new Error(uploadError.message);
      const {error}=await supabase.from("gameplay_uploads").insert({
        user_id:userId,storage_path:storagePath,
        title:String(form.get("title")||"").trim()||null,
        game_name:String(form.get("game")||"").trim()||"Grand Theft Auto VI",
        clip_count:Number(form.get("clips")||3)
      });
      if(error)throw new Error(error.message);
      setStatus({ok:"Uploaded. Highlights will be cut on the next worker run (within ~15 minutes)."});
      (event.target as HTMLFormElement).reset();
      router.refresh();
    }catch(error){setStatus({error:error instanceof Error?error.message:"Upload failed"});}
    finally{setBusy(false);}
  }

  return <form onSubmit={submit} className="mt-6 space-y-4">
    <label className="block text-sm text-zinc-400">Gameplay recording
      <input type="file" name="file" accept="video/*" required className={input}/>
    </label>
    <label className="block text-sm text-zinc-400">Title (optional)
      <input name="title" placeholder="Insane police chase in Vice City" className={input}/>
    </label>
    <div className="grid grid-cols-2 gap-4">
      <label className="block text-sm text-zinc-400">Game
        <input name="game" defaultValue="Grand Theft Auto VI" className={input}/>
      </label>
      <label className="block text-sm text-zinc-400">Highlights to cut
        <input name="clips" type="number" min={1} max={10} defaultValue={3} className={input}/>
      </label>
    </div>
    <button disabled={busy} className="rounded-xl bg-white px-6 py-3 font-semibold text-black disabled:opacity-50">{busy?"Uploading…":"Upload gameplay"}</button>
    {status.error&&<p className="text-sm text-red-400">{status.error}</p>}
    {status.ok&&<p className="text-sm text-emerald-400">{status.ok}</p>}
  </form>;
}
