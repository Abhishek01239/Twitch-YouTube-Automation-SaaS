import {createClient} from "@supabase/supabase-js";
import {generateMetadata} from "./lib/metadata";
import {execFile} from "node:child_process";
import {promises as fs} from "node:fs";
import os from "node:os";
import path from "node:path";

const DAY=24*60*60*1000;
const HOUR=60*60*1000;
const TIME_ZONE="America/New_York";
// Daily upload slots in New York time: 4 Shorts + 1 long-form video.
const SLOTS:Array<{hour:number;kind:"short"|"video"}>=[
  {hour:6,kind:"short"},
  {hour:9,kind:"short"},
  {hour:12,kind:"short"},
  {hour:15,kind:"short"},
  {hour:18,kind:"video"}
];
// A slot whose time already passed by more than this is skipped instead of uploaded late.
const LATE_TOLERANCE=45*60*1000;
// Build the daily compilation video this long before its slot.
const VIDEO_BUILD_LEAD=2*HOUR;
const VIDEO_MAX_CLIPS=10;
const VIDEO_MIN_CLIPS=2;

type Channel={id:string;name:string;youtube_channel_id:string;status:string};
type Job={id:string;source_short_id:string;channel_id:string;scheduled_at:string;status:string;attempts:number};
type YTToken={channel_id:string;access_token:string;refresh_token:string;token_expires_at:string|null};
type TwitchToken={connection_id:string;access_token:string;refresh_token:string;token_expires_at:string|null};
type Source={id:string;kind:"short"|"video";source_url:string|null;storage_path:string|null;edited_storage_path:string|null;title:string|null;description:string|null;tags:string[];hashtags:string[];created_at:string;compilation_date:string|null};

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

async function ingestTwitchClips(){
  const {data:connections}=await admin.from("twitch_connections").select("id,user_id,twitch_user_id,twitch_display_name");
  if(!connections?.length)return;
  const clientId=required("TWITCH_CLIENT_ID");
  const start=new Date(Date.now()-DAY).toISOString();

  for(const connection of connections as Array<{id:string;user_id:string;twitch_user_id:string;twitch_display_name:string}>){
    try{
      const {data:rawToken}=await admin.from("twitch_tokens").select("*").eq("connection_id",connection.id).single();
      if(!rawToken)continue;
      const token=await getUsableTwitchToken(rawToken as TwitchToken);
      const clipsUrl=new URL("https://api.twitch.tv/helix/clips");
      clipsUrl.searchParams.set("broadcaster_id",connection.twitch_user_id);
      clipsUrl.searchParams.set("started_at",start);
      clipsUrl.searchParams.set("first","20");
      const clipsResponse=await fetch(clipsUrl,{headers:{"Client-Id":clientId,Authorization:`Bearer ${token.access_token}`}});
      if(!clipsResponse.ok)throw new Error(`Twitch clips lookup failed: ${clipsResponse.status} ${await clipsResponse.text()}`);
      const clips=await clipsResponse.json() as {data:Array<{id:string;title:string;broadcaster_name:string;game_id:string;language:string;view_count:number;created_at:string;duration:number;video_id:string}>};

      const candidates=clips.data.sort((a,b)=>b.view_count-a.view_count).slice(0,10);
      if(!candidates.length)continue;

      const ids=candidates.map(c=>c.id);
      const downloadUrl=new URL("https://api.twitch.tv/helix/clips/downloads");
      downloadUrl.searchParams.set("broadcaster_id",connection.twitch_user_id);
      downloadUrl.searchParams.set("editor_id",connection.twitch_user_id);
      for(const id of ids)downloadUrl.searchParams.append("clip_id",id);

      const downloadsResponse=await fetch(downloadUrl,{headers:{"Client-Id":clientId,Authorization:`Bearer ${token.access_token}`}});
      if(!downloadsResponse.ok)throw new Error(`Twitch clip download lookup failed: ${downloadsResponse.status} ${await downloadsResponse.text()}`);
      const downloads=await downloadsResponse.json() as {data:Array<{clip_id:string;landscape_download_url:string|null;portrait_download_url:string|null}>};
      const byId=new Map(downloads.data.map(d=>[d.clip_id,d]));

      for(const clip of candidates){
        const media=byId.get(clip.id);
        const sourceUrl=media?.portrait_download_url||media?.landscape_download_url;
        if(!sourceUrl)continue;
        const exists=await admin.from("source_shorts").select("id").eq("source_url",sourceUrl).maybeSingle();
        if(exists.data)continue;

        const storagePath=await storeClip(connection.user_id,clip.id,sourceUrl);
        const meta=generateMetadata({channelName:connection.twitch_display_name,game:"Gaming",transcript:clip.title,keywords:["Twitch","Gaming","Shorts"]});
        const {error}=await admin.from("source_shorts").insert({
          source_url:sourceUrl,
          storage_path:storagePath,
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
    const vf=subtitlePath
      ?"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,subtitles="+subtitlePath.replace(/\\/g,"/").replace(/:/g,"\\:")+":force_style='FontName=DejaVu Sans,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=120'"
      :"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1";
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

function nyDateParts(date:Date){
  const parts=new Intl.DateTimeFormat("en-US",{timeZone:TIME_ZONE,year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",second:"2-digit",hourCycle:"h23"}).formatToParts(date);
  const get=(t:string)=>Number(parts.find(p=>p.type===t)?.value);
  return {year:get("year"),month:get("month"),day:get("day"),hour:get("hour"),minute:get("minute"),second:get("second")};
}
function tzOffsetMs(date:Date){
  const p=nyDateParts(date);
  return Date.UTC(p.year,p.month-1,p.day,p.hour,p.minute,p.second)-Math.floor(date.getTime()/1000)*1000;
}
// UTC instant for a wall-clock time in New York (DST-aware).
function nyTimeToUtc(year:number,month:number,day:number,hour:number){
  const guess=Date.UTC(year,month-1,day,hour,0,0);
  let utc=guess-tzOffsetMs(new Date(guess));
  utc=guess-tzOffsetMs(new Date(utc));
  return new Date(utc);
}
function todaysSlots(now:Date){
  const {year,month,day}=nyDateParts(now);
  const dateKey=`${year}-${String(month).padStart(2,"0")}-${String(day).padStart(2,"0")}`;
  return {dateKey,slots:SLOTS.map(s=>({...s,at:nyTimeToUtc(year,month,day,s.hour)}))};
}

function runFfmpeg(args:string[]){
  return new Promise<void>((resolve,reject)=>execFile("ffmpeg",args,{maxBuffer:10*1024*1024},e=>e?reject(e):resolve()));
}
function hasAudio(file:string){
  return new Promise<boolean>(resolve=>execFile("ffprobe",["-v","error","-select_streams","a","-show_entries","stream=index","-of","csv=p=0",file],(e,out)=>resolve(!e&&String(out).trim().length>0)));
}

// Builds a 16:9 long-form compilation of recent clips for today's video slot.
async function ensureDailyVideo(dateKey:string){
  const {data:existing}=await admin.from("source_shorts").select("*").eq("kind","video").eq("compilation_date",dateKey).maybeSingle();
  if(existing)return existing as Source;
  const {data:clips,error}=await admin.from("source_shorts").select("*").eq("kind","short").gte("created_at",new Date(Date.now()-DAY).toISOString()).order("created_at",{ascending:false}).limit(VIDEO_MAX_CLIPS);
  if(error)throw error;
  const list=(clips||[]) as Source[];
  if(list.length<VIDEO_MIN_CLIPS){console.log(`Not enough clips for ${dateKey} video (${list.length}).`);return null;}

  const dir=await fs.mkdtemp(path.join(os.tmpdir(),"daily-video-"));
  try{
    const parts:string[]=[];
    for(const [i,clip] of list.entries()){
      try{
        const {buffer}=await downloadVideo({...clip,edited_storage_path:null});
        const input=path.join(dir,`in-${i}.mp4`),out=path.join(dir,`part-${i}.mp4`);
        await fs.writeFile(input,buffer);
        const vf="scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p";
        const audioArgs=await hasAudio(input)
          ?["-i",input,"-vf",vf,"-map","0:v:0","-map","0:a:0"]
          :["-i",input,"-f","lavfi","-i","anullsrc=r=48000:cl=stereo","-vf",vf,"-map","0:v:0","-map","1:a:0","-shortest"];
        await runFfmpeg(["-y",...audioArgs,"-c:v","libx264","-preset","veryfast","-crf","22","-c:a","aac","-b:a","160k","-ar","48000","-ac","2",out]);
        parts.push(out);
      }catch(e){console.error(`Skipping clip ${clip.id} in compilation:`,e instanceof Error?e.message:String(e));}
    }
    if(parts.length<VIDEO_MIN_CLIPS){console.log(`Not enough usable clips for ${dateKey} video.`);return null;}
    const listFile=path.join(dir,"list.txt"),output=path.join(dir,"video.mp4");
    await fs.writeFile(listFile,parts.map(p=>`file '${p}'`).join("\n"),"utf8");
    await runFfmpeg(["-y","-f","concat","-safe","0","-i",listFile,"-c","copy","-movflags","+faststart",output]);
    const storagePath=`videos/${dateKey}-compilation.mp4`;
    const {error:uploadError}=await admin.storage.from(SOURCE_BUCKET).upload(storagePath,await fs.readFile(output),{contentType:"video/mp4",upsert:true});
    if(uploadError)throw new Error("Compilation storage upload failed: "+uploadError.message);
    const pretty=new Date(`${dateKey}T12:00:00Z`).toLocaleDateString("en-US",{month:"long",day:"numeric",year:"numeric",timeZone:"UTC"});
    const used=list.slice(0,parts.length);
    const description=`Best Twitch moments of ${pretty}.\n\n`+used.map((c,i)=>`${i+1}. ${c.title||"Clip"}`).join("\n");
    const {data:inserted,error:insertError}=await admin.from("source_shorts").insert({
      kind:"video",compilation_date:dateKey,storage_path:storagePath,source_url:null,
      title:`Best Twitch Moments – ${pretty}`.slice(0,100),
      description,
      tags:["Twitch","Gaming","Twitch highlights","Compilation","Best moments"],
      hashtags:["#Twitch","#Gaming","#Highlights"]
    }).select("*").single();
    if(insertError)throw insertError;
    console.log(`Daily video compiled for ${dateKey} from ${parts.length} clips.`);
    return inserted as Source;
  }finally{await fs.rm(dir,{recursive:true,force:true});}
}

// Fills today's New York slots (6am, 9am, 12pm, 3pm Shorts; 6pm video) for each channel.
async function scheduleTodaysSlots(channels:Channel[],shorts:Source[],video:Source|null,slots:Array<{hour:number;kind:"short"|"video";at:Date}>){
  const now=Date.now();
  const dayStart=slots[0].at.getTime()-HOUR,dayEnd=slots[slots.length-1].at.getTime()+HOUR;
  for(const channel of channels){
    const {data:existing}=await admin.from("upload_jobs").select("source_short_id,scheduled_at").eq("channel_id",channel.id).gte("scheduled_at",new Date(dayStart).toISOString()).lte("scheduled_at",new Date(dayEnd).toISOString());
    const takenTimes=new Set((existing||[]).map((j:{scheduled_at:string})=>new Date(j.scheduled_at).getTime()));
    const {data:used}=await admin.from("upload_jobs").select("source_short_id").eq("channel_id",channel.id).in("source_short_id",[...shorts.map(s=>s.id),...(video?[video.id]:[])]);
    const usedIds=new Set((used||[]).map((j:{source_short_id:string})=>j.source_short_id));
    const available=shorts.filter(s=>!usedIds.has(s.id));
    for(const slot of slots){
      const at=slot.at.getTime();
      if(takenTimes.has(at)||at<now-LATE_TOLERANCE)continue;
      const source=slot.kind==="video"?(video&&!usedIds.has(video.id)?video:null):available.shift();
      if(!source)continue;
      const {error}=await admin.from("upload_jobs").upsert({source_short_id:source.id,channel_id:channel.id,scheduled_at:slot.at.toISOString(),status:"pending"},{onConflict:"source_short_id,channel_id",ignoreDuplicates:true});
      if(error)console.error("schedule failed",channel.id,source.id,error.message);
      else console.log(`Scheduled ${slot.kind} for ${channel.name} at ${slot.hour}:00 ${TIME_ZONE}`);
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
      let uploadBuffer=buffer;
      if((source as Source).kind!=="video"){
        const editedPath=await ensureEditedAsset(source as Source,buffer);
        ({buffer:uploadBuffer}=await downloadVideo({...(source as Source),storage_path:editedPath,source_url:null}));
      }
      const videoId=await uploadToYouTube(usable.access_token,source as Source,uploadBuffer,"video/mp4");
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

  const {data:channels,error:channelError}=await admin.from("channels").select("id,name,youtube_channel_id,status").eq("status","active");
  if(channelError)throw channelError;
  const channelList=(channels||[]) as Channel[];if(!channelList.length){console.log("No active channels.");return;}

  const now=new Date();
  const {dateKey,slots}=todaysSlots(now);
  const {data:subs,error:subError}=await admin.from("subscriptions").select("channel_id,status,current_period_end").in("channel_id",channelList.map(c=>c.id)).eq("status","active");
  if(subError)throw subError;
  const ids=new Set((subs||[]).filter((s:{current_period_end:string|null})=>!s.current_period_end||new Date(s.current_period_end)>now).map((s:{channel_id:string})=>s.channel_id));
  const subscribed=channelList.filter(c=>ids.has(c.id));
  if(subscribed.length){
    const {data:shorts,error:sourceError}=await admin.from("source_shorts").select("*").eq("kind","short").gte("created_at",new Date(now.getTime()-2*DAY).toISOString()).order("created_at",{ascending:false}).limit(50);
    if(sourceError)throw sourceError;
    const videoSlot=slots.find(s=>s.kind==="video")!;
    let video:Source|null=null;
    if(now.getTime()>=videoSlot.at.getTime()-VIDEO_BUILD_LEAD&&now.getTime()<videoSlot.at.getTime()+LATE_TOLERANCE){
      try{video=await ensureDailyVideo(dateKey);}catch(e){console.error("Daily video build failed:",e instanceof Error?e.message:String(e));}
    }
    await scheduleTodaysSlots(subscribed,((shorts||[]) as Source[]).slice(0,50),video,slots);
  }
  await processDueJobs();
}
main().catch(error=>{console.error(error);process.exit(1);});
