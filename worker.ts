import {createClient} from "@supabase/supabase-js";
import {generateMetadata} from "./lib/metadata";
import {excitementCurve,pickCandidates,aiRank,type Segment} from "./lib/highlights";
import {execFile} from "node:child_process";
import {promises as fs} from "node:fs";
import os from "node:os";
import path from "node:path";

const DAY=24*60*60*1000;
const GAP=2*60*60*1000;
const MAX_PER_DAY=3;

type Channel={id:string;user_id:string;name:string;youtube_channel_id:string;status:string};
type Job={id:string;source_short_id:string;channel_id:string;scheduled_at:string;status:string;attempts:number};
type YTToken={channel_id:string;access_token:string;refresh_token:string;token_expires_at:string|null};
type TwitchToken={connection_id:string;access_token:string;refresh_token:string;token_expires_at:string|null};
type Source={id:string;source_url:string|null;storage_path:string|null;edited_storage_path:string|null;owner_user_id:string|null;source_kind:string;credit_text:string|null;title:string|null;description:string|null;tags:string[];hashtags:string[];created_at:string};

const admin=createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!,process.env.SUPABASE_SERVICE_ROLE_KEY!,{auth:{autoRefreshToken:false,persistSession:false}});
const required=(name:string)=>{const v=process.env[name];if(!v)throw new Error(`${name} is required`);return v;};

async function refreshGoogleToken(token:YTToken){
  const response=await fetch("https://oauth2.googleapis.com/token",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:new URLSearchParams({client_id:required("GOOGLE_CLIENT_ID"),client_secret:required("GOOGLE_CLIENT_SECRET"),refresh_token:token.refresh_token,grant_type:"refresh_token"})});
  if(!response.ok)throw new Error(`Google token refresh failed: ${await response.text()}`);
  const data=await response.json() as {access_token:string;expires_in:number};
  const expires=new Date(Date.now()+data.expires_in*1000).toISOString();
  await admin.from("youtube_tokens").update({access_token:data.access_token,token_expires_at:expires,updated_at:new Date().toISOString()}).eq("channel_id",token.channel_id);
  return {...token,access_token:data.access_token,token_expires_at:expires};
}
async function getUsableGoogleToken(token:YTToken){return !token.token_expires_at||new Date(token.token_expires_at).getTime()<=Date.now()+120000?refreshGoogleToken(token):token;}

async function refreshTwitchToken(token:TwitchToken){
  const response=await fetch("https://id.twitch.tv/oauth2/token",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:new URLSearchParams({client_id:required("TWITCH_CLIENT_ID"),client_secret:required("TWITCH_CLIENT_SECRET"),grant_type:"refresh_token",refresh_token:token.refresh_token})});
  if(!response.ok)throw new Error(`Twitch token refresh failed: ${await response.text()}`);
  const data=await response.json() as {access_token:string;refresh_token:string;expires_in:number;scope?:string[]};
  const expires=new Date(Date.now()+data.expires_in*1000).toISOString();
  await admin.from("twitch_tokens").update({access_token:data.access_token,refresh_token:data.refresh_token||token.refresh_token,token_expires_at:expires,scopes:data.scope||[],updated_at:new Date().toISOString()}).eq("connection_id",token.connection_id);
  return {...token,access_token:data.access_token,refresh_token:data.refresh_token||token.refresh_token,token_expires_at:expires};
}
async function getUsableTwitchToken(token:TwitchToken){return !token.token_expires_at||new Date(token.token_expires_at).getTime()<=Date.now()+120000?refreshTwitchToken(token):token;}

const SOURCE_BUCKET="source-clips";

async function storeClip(connectionUserId:string,clipId:string,sourceUrl:string){
  const response=await fetch(sourceUrl);
  if(!response.ok)throw new Error(`Twitch clip download failed: ${response.status}`);
  const buffer=Buffer.from(await response.arrayBuffer());
  if(!buffer.length)throw new Error("Twitch clip is empty");
  const storagePath=`clips/${connectionUserId}/${clipId}.mp4`;
  const {error}=await admin.storage.from(SOURCE_BUCKET).upload(storagePath,buffer,{contentType:"video/mp4",upsert:true});
  if(error)throw new Error(`Supabase Storage upload failed: ${error.message}`);
  return storagePath;
}

type TwitchClip={id:string;title:string;broadcaster_name:string;game_id:string;view_count:number;created_at:string;downloadUrl:string};

// Returns recent top clips with download URLs. Twitch only returns download URLs when the
// token owner (editorId) is the broadcaster or one of the broadcaster's channel editors.
async function fetchClipsWithDownloads(accessToken:string,broadcasterId:string,editorId:string,gameId?:string|null):Promise<TwitchClip[]>{
  const clientId=required("TWITCH_CLIENT_ID");
  const headers={"Client-Id":clientId,Authorization:`Bearer ${accessToken}`};
  const clipsUrl=new URL("https://api.twitch.tv/helix/clips");
  clipsUrl.searchParams.set("broadcaster_id",broadcasterId);
  clipsUrl.searchParams.set("started_at",new Date(Date.now()-DAY).toISOString());
  clipsUrl.searchParams.set("first","50");
  const clipsResponse=await fetch(clipsUrl,{headers});
  if(!clipsResponse.ok)throw new Error(`Twitch clips lookup failed: ${clipsResponse.status} ${await clipsResponse.text()}`);
  const clips=await clipsResponse.json() as {data:Array<Omit<TwitchClip,"downloadUrl">>};
  const candidates=clips.data.filter(c=>!gameId||c.game_id===gameId).sort((a,b)=>b.view_count-a.view_count).slice(0,10);
  if(!candidates.length)return [];

  const downloadUrl=new URL("https://api.twitch.tv/helix/clips/downloads");
  downloadUrl.searchParams.set("broadcaster_id",broadcasterId);
  downloadUrl.searchParams.set("editor_id",editorId);
  for(const c of candidates)downloadUrl.searchParams.append("clip_id",c.id);
  const downloadsResponse=await fetch(downloadUrl,{headers});
  if(downloadsResponse.status===401||downloadsResponse.status===403)throw new Error(`Not authorized to download clips for broadcaster ${broadcasterId}. The streamer must add your Twitch account as a channel editor, and you must reconnect Twitch to grant the editor:manage:clips scope.`);
  if(!downloadsResponse.ok)throw new Error(`Twitch clip download lookup failed: ${downloadsResponse.status} ${await downloadsResponse.text()}`);
  const downloads=await downloadsResponse.json() as {data:Array<{clip_id:string;landscape_download_url:string|null;portrait_download_url:string|null}>};
  const byId=new Map(downloads.data.map(d=>[d.clip_id,d]));
  return candidates.flatMap(c=>{const m=byId.get(c.id);const url=m?.portrait_download_url||m?.landscape_download_url;return url?[{...c,downloadUrl:url}]:[];});
}

type TwitchConnection={id:string;user_id:string;twitch_user_id:string;twitch_display_name:string};
async function connectionToken(connection:TwitchConnection){
  const {data:rawToken}=await admin.from("twitch_tokens").select("*").eq("connection_id",connection.id).single();
  return rawToken?getUsableTwitchToken(rawToken as TwitchToken):null;
}

async function ingestTwitchClips(){
  const {data:connections}=await admin.from("twitch_connections").select("id,user_id,twitch_user_id,twitch_display_name");
  if(!connections?.length)return;

  for(const connection of connections as TwitchConnection[]){
    try{
      const token=await connectionToken(connection);
      if(!token)continue;
      const clips=await fetchClipsWithDownloads(token.access_token,connection.twitch_user_id,connection.twitch_user_id);
      for(const clip of clips){
        const exists=await admin.from("source_shorts").select("id").eq("source_url",clip.downloadUrl).maybeSingle();
        if(exists.data)continue;

        const storagePath=await storeClip(connection.user_id,clip.id,clip.downloadUrl);
        const meta=generateMetadata({channelName:connection.twitch_display_name,game:"Gaming",transcript:clip.title,keywords:["Twitch","Gaming","Shorts"]});
        const {error}=await admin.from("source_shorts").insert({
          source_url:clip.downloadUrl,
          storage_path:storagePath,
          source_kind:"own_twitch",
          title:clip.title||meta.title,
          description:`Twitch clip by ${clip.broadcaster_name}. ${clip.title||""}`,
          tags:["Twitch","Gaming","YouTube Shorts",clip.broadcaster_name],
          hashtags:meta.hashtags
        });
        if(error)console.error("source insert failed",clip.id,error.message);
      }
    }catch(error){console.error(`Twitch ingestion failed for ${connection.twitch_display_name}:`,error instanceof Error?error.message:String(error));}
  }
}

type ApprovedStreamer={id:string;user_id:string;twitch_user_id:string;twitch_login:string;twitch_display_name:string;game_id:string|null;game_name:string|null};

// Clips from other streamers who gave this user permission (and made them a channel editor).
// These Shorts are only distributed to the approving user's own channels and carry a credit overlay.
async function ingestApprovedStreamerClips(){
  const {data:streamers,error}=await admin.from("approved_streamers").select("id,user_id,twitch_user_id,twitch_login,twitch_display_name,game_id,game_name").eq("active",true);
  if(error)throw error;
  if(!streamers?.length)return;
  const {data:connections}=await admin.from("twitch_connections").select("id,user_id,twitch_user_id,twitch_display_name").in("user_id",[...new Set(streamers.map(s=>s.user_id))]);
  const byUser=new Map((connections||[]).map((c:TwitchConnection)=>[c.user_id,c]));

  for(const streamer of streamers as ApprovedStreamer[]){
    try{
      const connection=byUser.get(streamer.user_id);
      if(!connection){console.error(`Skipping @${streamer.twitch_login}: user has no Twitch connection`);continue;}
      const token=await connectionToken(connection);
      if(!token)continue;
      const clips=await fetchClipsWithDownloads(token.access_token,streamer.twitch_user_id,connection.twitch_user_id,streamer.game_id);
      for(const clip of clips){
        const dedupeKey=`twitch:${streamer.user_id}:${clip.id}`;
        const exists=await admin.from("source_shorts").select("id").eq("dedupe_key",dedupeKey).maybeSingle();
        if(exists.data)continue;

        const storagePath=await storeClip(streamer.user_id,clip.id,clip.downloadUrl);
        const game=streamer.game_name||"Gaming";
        const meta=generateMetadata({channelName:streamer.twitch_display_name,game,transcript:clip.title,keywords:[game,streamer.twitch_display_name,"Shorts"]});
        const {error:insertError}=await admin.from("source_shorts").insert({
          storage_path:storagePath,
          dedupe_key:dedupeKey,
          owner_user_id:streamer.user_id,
          source_kind:"approved_streamer",
          credit_text:`twitch.tv/${streamer.twitch_login}`,
          title:clip.title||meta.title,
          description:`${game} clip from ${streamer.twitch_display_name}'s stream, shared with permission. Watch them live: https://twitch.tv/${streamer.twitch_login}`,
          tags:[...new Set([game,streamer.twitch_display_name,"Twitch","Gaming","YouTube Shorts"])],
          hashtags:meta.hashtags
        });
        if(insertError)console.error("approved streamer insert failed",clip.id,insertError.message);
      }
    }catch(error){console.error(`Approved streamer ingestion failed for @${streamer.twitch_login}:`,error instanceof Error?error.message:String(error));}
  }
}

const GAMEPLAY_BUCKET="gameplay-uploads";
const run=(cmd:string,args:string[])=>new Promise<{stdout:string;stderr:string}>((resolve,reject)=>execFile(cmd,args,{maxBuffer:64*1024*1024},(e,stdout,stderr)=>e?reject(new Error(`${cmd} failed: ${stderr.slice(-500)||e.message}`)):resolve({stdout,stderr})));

// Per-second loudness (RMS dBFS) of a recording's audio track.
async function loudnessPerSecond(input:string){
  const {stdout}=await run("ffmpeg",["-hide_banner","-nostats","-i",input,"-vn","-af","aresample=8000,asetnsamples=n=8000,astats=metadata=1:reset=1,ametadata=mode=print:key=lavfi.astats.Overall.RMS_level:file=-","-f","null","-"]);
  return [...stdout.matchAll(/RMS_level=(-?[\d.]+|-inf)/g)].map(m=>m[1]==="-inf"?-100:Math.max(-100,Number(m[1])));
}

// Per-second on-screen action: average pixel change between consecutive frames (chases, explosions,
// fast camera moves). Sampled at 4 fps on a tiny frame so long recordings stay cheap to analyze.
async function motionPerSecond(input:string,seconds:number){
  const {stdout}=await run("ffmpeg",["-hide_banner","-nostats","-i",input,"-an","-vf","fps=4,scale=160:-2,format=gray,tblend=all_mode=difference,signalstats,metadata=mode=print:key=lavfi.signalstats.YAVG:file=-","-f","null","-"]);
  const sum=new Array(seconds).fill(0),count=new Array(seconds).fill(0);let time=0;
  for(const line of stdout.split("\n")){
    const t=line.match(/pts_time:([\d.]+)/);if(t)time=Number(t[1]);
    const v=line.match(/YAVG=([\d.]+)/);
    if(v){const i=Math.floor(time);if(i<seconds){sum[i]+=Number(v[1]);count[i]++;}}
  }
  return sum.map((s,i)=>count[i]?s/count[i]:0);
}

// Full-recording transcript, in 10-minute chunks so long streams stay under the API's file limit.
async function transcribeRecording(input:string,seconds:number,dir:string):Promise<Segment[]>{
  if(!process.env.GROQ_API_KEY)return [];
  const segments:Segment[]=[];
  for(let offset=0;offset<seconds;offset+=600){
    const chunk=path.join(dir,`audio-${offset}.mp3`);
    try{
      await run("ffmpeg",["-y","-ss",String(offset),"-t","600","-i",input,"-vn","-ac","1","-ar","16000","-b:a","48k",chunk]);
      const form=new FormData();
      form.append("file",new Blob([await fs.readFile(chunk)],{type:"audio/mpeg"}),"audio.mp3");
      form.append("model",process.env.GROQ_WHISPER_MODEL||"whisper-large-v3-turbo");
      form.append("response_format","verbose_json");
      form.append("timestamp_granularities[]","segment");
      form.append("temperature","0");
      const response=await fetch("https://api.groq.com/openai/v1/audio/transcriptions",{method:"POST",headers:{Authorization:"Bearer "+process.env.GROQ_API_KEY},body:form});
      if(!response.ok)throw new Error(`${response.status} ${await response.text()}`);
      const data=await response.json() as {segments?:Segment[]};
      for(const seg of data.segments||[])segments.push({start:seg.start+offset,end:seg.end+offset,text:seg.text});
    }catch(error){console.error(`Transcription chunk at ${offset}s failed:`,error instanceof Error?error.message:String(error));}
    finally{await fs.rm(chunk,{force:true});}
  }
  return segments;
}

// Finds the most exciting moments: audio spikes, on-screen action and hype speech, then an AI judge
// picks the clips most likely to perform and titles them.
async function findHighlights(input:string,dir:string,opts:{length:number;count:number;game:string}){
  const loudness=await loudnessPerSecond(input);
  if(!loudness.length)throw new Error("Recording has no audio track to detect highlights from");
  const [motion,segments]=await Promise.all([
    motionPerSecond(input,loudness.length).catch(e=>{console.error("Motion analysis failed:",e.message);return [] as number[];}),
    transcribeRecording(input,loudness.length,dir)
  ]);
  const curve=excitementCurve({loudness,motion,segments});
  const candidates=pickCandidates(curve,{length:opts.length,count:opts.count*3,segments});
  return aiRank(candidates,opts.count,{game:opts.game,apiKey:process.env.GROQ_API_KEY,model:process.env.GROQ_LLM_MODEL});
}

type GameplayUpload={id:string;user_id:string;storage_path:string;title:string|null;game_name:string;clip_count:number;clip_seconds:number};

async function processGameplayUploads(){
  const {data:uploads,error}=await admin.from("gameplay_uploads").select("id,user_id,storage_path,title,game_name,clip_count,clip_seconds").eq("status","pending").order("created_at",{ascending:true}).limit(3);
  if(error)throw error;
  for(const upload of (uploads||[]) as GameplayUpload[]){
    const {data:claimed}=await admin.from("gameplay_uploads").update({status:"processing",last_error:null}).eq("id",upload.id).eq("status","pending").select("id").maybeSingle();
    if(!claimed)continue;
    const dir=await fs.mkdtemp(path.join(os.tmpdir(),"gameplay-"));
    try{
      const {data,error:downloadError}=await admin.storage.from(GAMEPLAY_BUCKET).download(upload.storage_path);
      if(downloadError||!data)throw new Error(`Gameplay download failed: ${downloadError?.message||"missing file"}`);
      const input=path.join(dir,"input"+(path.extname(upload.storage_path)||".mp4"));
      await fs.writeFile(input,Buffer.from(await data.arrayBuffer()));

      const highlights=await findHighlights(input,dir,{length:upload.clip_seconds,count:upload.clip_count,game:upload.game_name});
      let created=0;
      for(const [i,clip] of highlights.entries()){
        const dedupeKey=`gameplay:${upload.id}:${i}`;
        const exists=await admin.from("source_shorts").select("id").eq("dedupe_key",dedupeKey).maybeSingle();
        if(exists.data){created++;continue;}
        const clipPath=path.join(dir,`clip-${i}.mp4`);
        await run("ffmpeg",["-y","-ss",clip.start.toFixed(2),"-i",input,"-t",(clip.end-clip.start).toFixed(2),"-c:v","libx264","-preset","veryfast","-crf","20","-c:a","aac","-b:a","160k","-movflags","+faststart",clipPath]);
        const storagePath=`gameplay/${upload.user_id}/${upload.id}-${i}.mp4`;
        const {error:storeError}=await admin.storage.from(SOURCE_BUCKET).upload(storagePath,await fs.readFile(clipPath),{contentType:"video/mp4",upsert:true});
        if(storeError)throw new Error(`Highlight storage upload failed: ${storeError.message}`);
        const meta=generateMetadata({channelName:upload.title||upload.game_name,game:upload.game_name,keywords:[upload.game_name,"gameplay","highlights"]});
        const {error:insertError}=await admin.from("source_shorts").insert({
          storage_path:storagePath,
          dedupe_key:dedupeKey,
          owner_user_id:upload.user_id,
          source_kind:"own_gameplay",
          title:(clip.title||(upload.title?`${upload.title} #${i+1}`:meta.title)).slice(0,100),
          description:meta.description,
          tags:meta.tags,
          hashtags:meta.hashtags
        });
        if(insertError)throw new Error(`Highlight insert failed: ${insertError.message}`);
        created++;
      }
      await admin.from("gameplay_uploads").update({status:"done",clips_created:created}).eq("id",upload.id);
      console.log(`Cut ${created} highlights from gameplay upload ${upload.id}:`,highlights.map(h=>`${Math.round(h.start)}s-${Math.round(h.end)}s${h.reason?` (${h.reason})`:""}`).join(", "));
    }catch(error){
      const message=error instanceof Error?error.message:String(error);
      await admin.from("gameplay_uploads").update({status:"failed",last_error:message}).eq("id",upload.id);
      console.error(`Gameplay upload ${upload.id} failed:`,message);
    }finally{await fs.rm(dir,{recursive:true,force:true});}
  }
}

type TranscriptSegment={start:number;end:number;text:string};

function srtTime(seconds:number){
  const ms=Math.max(0,Math.round(seconds*1000));
  const h=Math.floor(ms/3600000),m=Math.floor((ms%3600000)/60000),s=Math.floor((ms%60000)/1000),milli=ms%1000;
  return String(h).padStart(2,"0")+":"+String(m).padStart(2,"0")+":"+String(s).padStart(2,"0")+","+String(milli).padStart(3,"0");
}
function makeSrt(segments:TranscriptSegment[]){
  return segments.filter(s=>s.text?.trim()).map((s,i)=>(i+1)+"\n"+srtTime(s.start)+" --> "+srtTime(Math.max(s.end,s.start+0.5))+"\n"+s.text.trim()+"\n").join("\n");
}
async function transcribeWithGroq(video:Buffer){
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),"groq-audio-"));
  const input=path.join(dir,"input.mp4"),audio=path.join(dir,"audio.mp3");
  try{
    await fs.writeFile(input,video);
    await new Promise<void>((resolve,reject)=>execFile("ffmpeg",["-y","-i",input,"-vn","-ac","1","-ar","16000","-b:a","64k",audio],{maxBuffer:1024*1024},e=>e?reject(e):resolve()));
    const form=new FormData();
    form.append("file",new Blob([await fs.readFile(audio)],{type:"audio/mpeg"}),"audio.mp3");
    form.append("model",process.env.GROQ_WHISPER_MODEL||"whisper-large-v3-turbo");
    form.append("response_format","verbose_json");
    form.append("timestamp_granularities[]","segment");
    form.append("temperature","0");
    const response=await fetch("https://api.groq.com/openai/v1/audio/transcriptions",{method:"POST",headers:{Authorization:"Bearer "+required("GROQ_API_KEY")},body:form});
    if(!response.ok)throw new Error("Groq transcription failed: "+response.status+" "+await response.text());
    const data=await response.json() as {text?:string;segments?:TranscriptSegment[]};
    return {text:data.text||"",segments:data.segments||[]};
  }finally{await fs.rm(dir,{recursive:true,force:true});}
}

async function makeVerticalShort(source:Source,video:Buffer,subtitlePath?:string){
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),"twitch-short-"));
  const input=path.join(dir,"input.mp4"),output=path.join(dir,"output.mp4");
  try{
    await fs.writeFile(input,video);
    let vf=subtitlePath
      ?"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,subtitles="+subtitlePath.replace(/\\/g,"/").replace(/:/g,"\\:")+":force_style='FontName=DejaVu Sans,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=120'"
      :"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1";
    if(source.credit_text){
      const creditFile=path.join(dir,"credit.txt");
      await fs.writeFile(creditFile,source.credit_text,"utf8");
      vf+=",drawtext=textfile="+creditFile.replace(/\\/g,"/").replace(/:/g,"\\:")+":font='DejaVu Sans':fontsize=44:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=14:x=(w-text_w)/2:y=110";
    }
    await new Promise<void>((resolve,reject)=>execFile("ffmpeg",["-y","-i",input,"-vf",vf,"-c:v","libx264","-preset","veryfast","-crf","23","-c:a","aac","-b:a","128k","-movflags","+faststart",output],{maxBuffer:1024*1024},e=>e?reject(e):resolve()));
    return await fs.readFile(output);
  }finally{await fs.rm(dir,{recursive:true,force:true});}
}

async function ensureEditedAsset(source:Source,video:Buffer){
  if(source.edited_storage_path)return source.edited_storage_path;
  const transcript=await transcribeWithGroq(video);
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),"captions-")),srt=path.join(dir,"captions.srt");
  try{
    await fs.writeFile(srt,makeSrt(transcript.segments),"utf8");
    const edited=await makeVerticalShort(source,video,transcript.segments.length?srt:undefined);
    const storagePath=source.storage_path?source.storage_path.replace(/^clips\//,"edited/").replace(/\.mp4$/i,"-9x16-captioned.mp4"):"edited/"+source.id+"-9x16-captioned.mp4";
    const {error}=await admin.storage.from(SOURCE_BUCKET).upload(storagePath,edited,{contentType:"video/mp4",upsert:true});
    if(error)throw new Error("Edited short storage upload failed: "+error.message);
    const {error:updateError}=await admin.from("source_shorts").update({edited_storage_path:storagePath}).eq("id",source.id);
    if(updateError)throw updateError;
    console.log("Captioned short created for "+source.id+": "+transcript.text.slice(0,120));
    return storagePath;
  }finally{await fs.rm(dir,{recursive:true,force:true});}
}

async function downloadVideo(source:Source){
  if(source.storage_path && !source.storage_path.startsWith("http")){
    const {data,error}=await admin.storage.from(SOURCE_BUCKET).download(source.storage_path);
    if(error||!data)throw new Error(`Source video storage download failed: ${error?.message||"missing file"}`);
    const buffer=Buffer.from(await data.arrayBuffer());
    if(!buffer.length)throw new Error("Stored source video is empty");
    return {buffer,contentType:"video/mp4"};
  }
  if(!source.source_url)throw new Error("Source Short has no downloadable source");
  const response=await fetch(source.source_url);
  if(!response.ok)throw new Error(`Source video download failed: ${response.status}`);
  const buffer=Buffer.from(await response.arrayBuffer());
  if(!buffer.length)throw new Error("Source video is empty");
  return {buffer,contentType:(response.headers.get("content-type")||"video/mp4").split(";")[0]};
}

async function uploadToYouTube(token:string,source:Source,video:Buffer,contentType:string){
  const generated=generateMetadata({channelName:source.title||"Gaming",game:"Gaming",transcript:source.description||"",keywords:source.tags||[]});
  const title=(source.title||generated.title).slice(0,100);
  const description=((source.description||generated.description)+"\n\n"+(source.hashtags||generated.hashtags).join(" ")).slice(0,5000);
  const tags=(source.tags?.length?source.tags:generated.tags).slice(0,100);
  const init=await fetch("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",{method:"POST",headers:{Authorization:`Bearer ${token}`,"Content-Type":"application/json; charset=UTF-8","X-Upload-Content-Length":String(video.length),"X-Upload-Content-Type":contentType},body:JSON.stringify({snippet:{title,description,tags,categoryId:"20"},status:{privacyStatus:"public",selfDeclaredMadeForKids:false}})});
  if(!init.ok)throw new Error(`YouTube upload session failed: ${init.status} ${await init.text()}`);
  const uploadUrl=init.headers.get("location");if(!uploadUrl)throw new Error("YouTube did not return an upload session URL");
  const uploadBody=new ArrayBuffer(video.byteLength); new Uint8Array(uploadBody).set(video); const put=await fetch(uploadUrl,{method:"PUT",headers:{Authorization:`Bearer ${token}`,"Content-Type":contentType,"Content-Length":String(video.length),"Content-Range":`bytes 0-${video.length-1}/${video.length}`},body:uploadBody});
  if(!put.ok)throw new Error(`YouTube video upload failed: ${put.status} ${await put.text()}`);
  const result=await put.json() as {id?:string};if(!result.id)throw new Error("YouTube upload completed without a video id");return result.id;
}

async function scheduleTodaysShorts(channels:Channel[],sources:Source[]){
  const start=new Date();start.setUTCHours(0,0,0,0);const end=new Date(start.getTime()+DAY);
  for(const channel of channels){
    const {data:existing}=await admin.from("upload_jobs").select("source_short_id,scheduled_at,status").eq("channel_id",channel.id).gte("scheduled_at",start.toISOString()).lt("scheduled_at",end.toISOString()).order("scheduled_at",{ascending:true});
    const existingIds=new Set((existing||[]).map((j:{source_short_id:string})=>j.source_short_id));
    // Clips from approved streamers and own gameplay belong to one user: only that user's channels get them.
    const missing=sources.filter(s=>!existingIds.has(s.id)&&(!s.owner_user_id||s.owner_user_id===channel.user_id)).slice(0,MAX_PER_DAY);if(!missing.length)continue;
    let next=Math.max(Date.now(),(existing||[]).reduce((max:number,j:{scheduled_at:string})=>Math.max(max,new Date(j.scheduled_at).getTime()),0)+GAP);
    for(const source of missing){
      const {error}=await admin.from("upload_jobs").upsert({source_short_id:source.id,channel_id:channel.id,scheduled_at:new Date(next).toISOString(),status:"pending"},{onConflict:"source_short_id,channel_id"});
      if(error)console.error("schedule failed",channel.id,source.id,error.message);next+=GAP;
    }
  }
}

async function processDueJobs(){
  const {data:jobs,error}=await admin.from("upload_jobs").select("id,source_short_id,channel_id,scheduled_at,status,attempts").eq("status","pending").lte("scheduled_at",new Date().toISOString()).order("scheduled_at",{ascending:true}).limit(25);
  if(error)throw error;
  for(const job of (jobs||[]) as Job[]){
    const {data:claimed}=await admin.from("upload_jobs").update({status:"processing",attempts:job.attempts+1,last_error:null}).eq("id",job.id).eq("status","pending").select("id").maybeSingle();
    if(!claimed)continue;
    try{
      const [{data:source},{data:channel},{data:token}]=await Promise.all([
        admin.from("source_shorts").select("*").eq("id",job.source_short_id).single(),
        admin.from("channels").select("id,name,youtube_channel_id,status").eq("id",job.channel_id).single(),
        admin.from("youtube_tokens").select("*").eq("channel_id",job.channel_id).single()
      ]);
      if(!source||!channel||!token)throw new Error("Missing source, channel, or YouTube OAuth token");
      if(channel.status!=="active")throw new Error("Channel is not active");
      const usable=await getUsableGoogleToken(token as YTToken);
      const {buffer,contentType}=await downloadVideo(source as Source);
      await ensureEditedAsset(source as Source,buffer);
      const editedSource={...(source as Source),storage_path:(source as Source).edited_storage_path||undefined,source_url:null};
      const {buffer:editedBuffer}=await downloadVideo({...editedSource,edited_storage_path:(await admin.from("source_shorts").select("edited_storage_path").eq("id",source.id).single()).data?.edited_storage_path||null} as Source);
      const videoId=await uploadToYouTube(usable.access_token,source as Source,editedBuffer,"video/mp4");
      await admin.from("upload_jobs").update({status:"uploaded",youtube_video_id:videoId,last_error:null}).eq("id",job.id);
      console.log(`Uploaded ${videoId} to ${channel.name}`);
    }catch(error){
      const message=error instanceof Error?error.message:String(error);
      await admin.from("upload_jobs").update({status:job.attempts+1>=3?"failed":"pending",last_error:message}).eq("id",job.id);
      console.error(`Job ${job.id} failed:`,message);
    }
  }
}

async function main(){
  required("NEXT_PUBLIC_SUPABASE_URL");required("SUPABASE_SERVICE_ROLE_KEY");required("GOOGLE_CLIENT_ID");required("GOOGLE_CLIENT_SECRET");required("TWITCH_CLIENT_ID");required("TWITCH_CLIENT_SECRET");required("GROQ_API_KEY");
  await ingestTwitchClips();
  await ingestApprovedStreamerClips().catch(e=>console.error("Approved streamer ingestion failed:",e instanceof Error?e.message:String(e)));
  await processGameplayUploads().catch(e=>console.error("Gameplay processing failed:",e instanceof Error?e.message:String(e)));

  const {data:channels,error:channelError}=await admin.from("channels").select("id,user_id,name,youtube_channel_id,status").eq("status","active");
  if(channelError)throw channelError;
  const channelList=(channels||[]) as Channel[];if(!channelList.length){console.log("No active channels.");return;}

  const now=new Date();const start=new Date(now);start.setUTCHours(0,0,0,0);
  const {data:sources,error:sourceError}=await admin.from("source_shorts").select("*").gte("created_at",start.toISOString()).lt("created_at",new Date(start.getTime()+DAY).toISOString()).order("created_at",{ascending:false}).limit(200);
  if(sourceError)throw sourceError;
  const todaysSources=(sources||[]) as Source[];
  if(todaysSources.length){
    const {data:subs,error:subError}=await admin.from("subscriptions").select("channel_id,status,current_period_end").in("channel_id",channelList.map(c=>c.id)).eq("status","active");
    if(subError)throw subError;
    const ids=new Set((subs||[]).filter((s:{current_period_end:string|null})=>!s.current_period_end||new Date(s.current_period_end)>now).map((s:{channel_id:string})=>s.channel_id));
    await scheduleTodaysShorts(channelList.filter(c=>ids.has(c.id)),todaysSources);
  }
  await processDueJobs();
}
main().catch(error=>{console.error(error);process.exit(1);});
