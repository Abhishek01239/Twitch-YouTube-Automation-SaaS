"use server";
import {revalidatePath} from "next/cache";
import {createClient} from "../../lib/supabase/server";

async function twitchAppToken(){
  const clientId=process.env.TWITCH_CLIENT_ID,clientSecret=process.env.TWITCH_CLIENT_SECRET;
  if(!clientId||!clientSecret)throw new Error("Twitch is not configured");
  const response=await fetch("https://id.twitch.tv/oauth2/token",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body:new URLSearchParams({client_id:clientId,client_secret:clientSecret,grant_type:"client_credentials"})});
  if(!response.ok)throw new Error("Could not reach Twitch");
  const {access_token}=await response.json() as {access_token:string};
  return {clientId,headers:{"Client-Id":clientId,Authorization:`Bearer ${access_token}`}};
}

export type ActionState={error?:string;ok?:string};

export async function addApprovedStreamer(_prev:ActionState,form:FormData):Promise<ActionState>{
  const supabase=await createClient();
  const {data:{user}}=await supabase.auth.getUser();
  if(!user)return {error:"Please log in again."};

  const login=String(form.get("login")||"").trim().replace(/^@/,"").replace(/^https?:\/\/(www\.)?twitch\.tv\//i,"").split(/[/?#]/)[0].toLowerCase();
  const permission=String(form.get("permission")||"").trim();
  const gameName=String(form.get("game")||"").trim();
  if(!/^[a-z0-9_]{3,25}$/.test(login))return {error:"Enter a valid Twitch username."};
  if(!permission)return {error:"Describe how the streamer gave you permission (e.g. link to their message)."};
  if(form.get("confirm")!=="on")return {error:"You must confirm the streamer gave you permission."};

  try{
    const {headers}=await twitchAppToken();
    const usersResponse=await fetch(`https://api.twitch.tv/helix/users?login=${encodeURIComponent(login)}`,{headers});
    const users=await usersResponse.json() as {data?:Array<{id:string;login:string;display_name:string}>};
    const streamer=users.data?.[0];
    if(!streamer)return {error:`Twitch user @${login} not found.`};

    let game:{id:string;name:string}|undefined;
    if(gameName){
      const gamesResponse=await fetch(`https://api.twitch.tv/helix/games?name=${encodeURIComponent(gameName)}`,{headers});
      game=(await gamesResponse.json() as {data?:Array<{id:string;name:string}>}).data?.[0];
      if(!game)return {error:`Game "${gameName}" not found on Twitch. Use the exact Twitch category name, e.g. "Grand Theft Auto VI".`};
    }

    const {error}=await supabase.from("approved_streamers").upsert({
      user_id:user.id,twitch_user_id:streamer.id,twitch_login:streamer.login,twitch_display_name:streamer.display_name,
      permission_note:permission,game_id:game?.id||null,game_name:game?.name||null,active:true
    },{onConflict:"user_id,twitch_user_id"});
    if(error)return {error:error.message};
    revalidatePath("/dashboard");
    return {ok:`Added @${streamer.login}. Ask them to add your Twitch account as an editor (Creator Dashboard → Settings → Roles Manager) so clips can be fetched.`};
  }catch(error){return {error:error instanceof Error?error.message:"Something went wrong"};}
}

export async function setStreamerActive(id:string,active:boolean){
  const supabase=await createClient();
  await supabase.from("approved_streamers").update({active}).eq("id",id);
  revalidatePath("/dashboard");
}
