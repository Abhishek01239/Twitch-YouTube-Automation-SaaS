import {createClient} from "@supabase/supabase-js";
import {generateMetadata} from "./lib/metadata";

const DAY=24*60*60*1000;
const GAP=2*60*60*1000;
const MAX_PER_DAY=3;

type Channel={id:string;name:string;youtube_channel_id:string;status:string};
type Job={id:string;source_short_id:string;channel_id:string;scheduled_at:string;status:string;attempts:number};
type Token={channel_id:string;access_token:string;refresh_token:string;token_expires_at:string|null};
type Source={id:string;source_url:string|null;storage_path:string|null;title:string|null;description:string|null;tags:string[];hashtags:string[];created_at:string};

const admin=createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!,
  {auth:{autoRefreshToken:false,persistSession:false}}
);

function required(name:string){
  const value=process.env[name];
  if(!value) throw new Error(`${name} is required`);
  return value;
}

async function refreshGoogleToken(token:Token){
  const response=await fetch("https://oauth2.googleapis.com/token",{
    method:"POST",
    headers:{"Content-Type":"application/x-www-form-urlencoded"},
    body:new URLSearchParams({
      client_id:required("GOOGLE_CLIENT_ID"),
      client_secret:required("GOOGLE_CLIENT_SECRET"),
      refresh_token:token.refresh_token,
      grant_type:"refresh_token"
    })
  });
  if(!response.ok) throw new Error(`Google token refresh failed: ${await response.text()}`);
  const data=await response.json() as {access_token:string;expires_in:number;scope?:string};
  const expires=new Date(Date.now()+data.expires_in*1000).toISOString();
  await admin.from("youtube_tokens").update({access_token:data.access_token,token_expires_at:expires,updated_at:new Date().toISOString()}).eq("channel_id",token.channel_id);
  return {...token,access_token:data.access_token,token_expires_at:expires};
}

async function getUsableToken(token:Token){
  if(!token.token_expires_at || new Date(token.token_expires_at).getTime()<=Date.now()+120000){
    return refreshGoogleToken(token);
  }
  return token;
}

async function downloadVideo(source:Source){
  const url=source.source_url || (source.storage_path?.startsWith("http") ? source.storage_path : null);
  if(!url) throw new Error("Source Short has no downloadable source_url");
  const response=await fetch(url);
  if(!response.ok) throw new Error(`Source video download failed: ${response.status}`);
  const buffer=Buffer.from(await response.arrayBuffer());
  if(buffer.length===0) throw new Error("Source video is empty");
  const contentType=(response.headers.get("content-type")||"video/mp4").split(";")[0];
  return {buffer,contentType};
}

async function uploadToYouTube(token:string,source:Source,video:Buffer,contentType:string){
  const generated=generateMetadata({
    channelName:source.title||"Gaming",
    game:"Gaming",
    transcript:source.description||"",
    keywords:source.tags||[]
  });
  const title=(source.title || generated.title).slice(0,100);
  const description=((source.description || generated.description)+"\n\n"+(source.hashtags||generated.hashtags).join(" ")).slice(0,5000);
  const tags=(source.tags?.length ? source.tags : generated.tags).slice(0,100);

  const metadata={
    snippet:{title,description,tags,categoryId:"20"},
    status:{privacyStatus:"public",selfDeclaredMadeForKids:false}
  };

  const init=await fetch("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",{
    method:"POST",
    headers:{
      Authorization:`Bearer ${token}`,
      "Content-Type":"application/json; charset=UTF-8",
      "X-Upload-Content-Length":String(video.length),
      "X-Upload-Content-Type":contentType
    },
    body:JSON.stringify(metadata)
  });
  if(!init.ok) throw new Error(`YouTube upload session failed: ${init.status} ${await init.text()}`);
  const uploadUrl=init.headers.get("location");
  if(!uploadUrl) throw new Error("YouTube did not return an upload session URL");

  const put=await fetch(uploadUrl,{
    method:"PUT",
    headers:{
      Authorization:`Bearer ${token}`,
      "Content-Type":contentType,
      "Content-Length":String(video.length),
      "Content-Range":`bytes 0-${video.length-1}/${video.length}`
    },
    body:video
  });
  if(!put.ok) throw new Error(`YouTube video upload failed: ${put.status} ${await put.text()}`);
  const result=await put.json() as {id?:string};
  if(!result.id) throw new Error("YouTube upload completed without a video id");
  return result.id;
}

async function scheduleTodaysShorts(channels:Channel[],sources:Source[]){
  const todayStart=new Date();
  todayStart.setUTCHours(0,0,0,0);
  const tomorrow=new Date(todayStart.getTime()+DAY);

  for(const channel of channels){
    const {data:existing}=await admin.from("upload_jobs")
      .select("source_short_id,scheduled_at,status")
      .eq("channel_id",channel.id)
      .gte("scheduled_at",todayStart.toISOString())
      .lt("scheduled_at",tomorrow.toISOString())
      .order("scheduled_at",{ascending:true});

    const existingIds=new Set((existing||[]).map((j:{source_short_id:string})=>j.source_short_id));
    const missing=sources.filter(s=>!existingIds.has(s.id)).slice(0,MAX_PER_DAY);
    if(!missing.length) continue;

    let next=Date.now();
    const latest=(existing||[]).reduce((max:number,j:{scheduled_at:string})=>Math.max(max,new Date(j.scheduled_at).getTime()),0);
    if(latest) next=Math.max(next,latest+GAP);

    for(const source of missing){
      const scheduledAt=new Date(next).toISOString();
      const {error}=await admin.from("upload_jobs").upsert({
        source_short_id:source.id,
        channel_id:channel.id,
        scheduled_at:scheduledAt,
        status:"pending"
      },{onConflict:"source_short_id,channel_id"});
      if(error) console.error("schedule failed",channel.id,source.id,error.message);
      next+=GAP;
    }
  }
}

async function processDueJobs(){
  const now=new Date().toISOString();
  const {data:jobs,error}=await admin.from("upload_jobs")
    .select("id,source_short_id,channel_id,scheduled_at,status,attempts")
    .eq("status","pending")
    .lte("scheduled_at",now)
    .order("scheduled_at",{ascending:true})
    .limit(25);
  if(error) throw error;

  for(const job of (jobs||[]) as Job[]){
    const {data:claimed}=await admin.from("upload_jobs").update({
      status:"processing",
      attempts:job.attempts+1,
      last_error:null
    }).eq("id",job.id).eq("status","pending").select("id").maybeSingle();
    if(!claimed) continue;

    try{
      const [{data:source},{data:channel},{data:token}]=await Promise.all([
        admin.from("source_shorts").select("*").eq("id",job.source_short_id).single(),
        admin.from("channels").select("id,name,youtube_channel_id,status").eq("id",job.channel_id).single(),
        admin.from("youtube_tokens").select("*").eq("channel_id",job.channel_id).single()
      ]);
      if(!source || !channel || !token) throw new Error("Missing source, channel, or YouTube OAuth token");
      if(channel.status!=="active") throw new Error("Channel is not active");
      const usable=await getUsableToken(token as Token);
      const {buffer,contentType}=await downloadVideo(source as Source);
      const videoId=await uploadToYouTube(usable.access_token,source as Source,buffer,contentType);
      await admin.from("upload_jobs").update({status:"uploaded",youtube_video_id:videoId,last_error:null}).eq("id",job.id);
      console.log(`Uploaded ${videoId} to ${channel.name}`);
    }catch(error){
      const message=error instanceof Error?error.message:String(error);
      await admin.from("upload_jobs").update({
        status:job.attempts+1>=3?"failed":"pending",
        last_error:message
      }).eq("id",job.id);
      console.error(`Job ${job.id} failed:`,message);
    }
  }
}

async function main(){
  required("NEXT_PUBLIC_SUPABASE_URL");
  required("SUPABASE_SERVICE_ROLE_KEY");
  required("GOOGLE_CLIENT_ID");
  required("GOOGLE_CLIENT_SECRET");

  const {data:channels,error:channelError}=await admin
    .from("channels")
    .select("id,name,youtube_channel_id,status")
    .eq("status","active");
  if(channelError) throw channelError;

  const channelList=(channels||[]) as Channel[];
  if(!channelList.length){
    console.log("No active channels.");
    return;
  }

  const now=new Date();
  const todayStart=new Date(now);
  todayStart.setUTCHours(0,0,0,0);
  const {data:sources,error:sourceError}=await admin
    .from("source_shorts")
    .select("*")
    .gte("created_at",todayStart.toISOString())
    .lt("created_at",new Date(todayStart.getTime()+DAY).toISOString())
    .order("created_at",{ascending:false})
    .limit(MAX_PER_DAY);
  if(sourceError) throw sourceError;

  const todaysSources=(sources||[]) as Source[];
  if(todaysSources.length){
    const {data:subs,error:subError}=await admin
      .from("subscriptions")
      .select("channel_id,status,current_period_end")
      .in("channel_id",channelList.map(c=>c.id))
      .eq("status","active");
    if(subError) throw subError;
    const subscribedIds=new Set((subs||[]).filter((s:{current_period_end:string|null})=>!s.current_period_end || new Date(s.current_period_end)>now).map((s:{channel_id:string})=>s.channel_id));
    await scheduleTodaysShorts(channelList.filter(c=>subscribedIds.has(c.id)),todaysSources);
  }

  await processDueJobs();
}

main().catch(error=>{
  console.error(error);
  process.exit(1);
});
