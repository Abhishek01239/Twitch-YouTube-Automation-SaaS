import {NextResponse} from "next/server";
import {cookies} from "next/headers";
import {createClient} from "@/lib/supabase/server";
import {createClient as createSupabaseAdmin} from "@supabase/supabase-js";

type TokenResponse={access_token:string;refresh_token?:string;expires_in:number;scope?:string};
type ChannelResponse={items?:Array<{id:string;snippet?:{title?:string}}>} ;

export async function GET(request:Request){
  const url=new URL(request.url);
  const code=url.searchParams.get("code");
  const state=url.searchParams.get("state");
  const oauthError=url.searchParams.get("error");
  const supabase=await createClient();
  const {data:{user}}=await supabase.auth.getUser();
  if(!user) return NextResponse.redirect(new URL("/login",request.url));

  const cookieStore=await cookies();
  const expectedState=cookieStore.get("youtube_oauth_state")?.value;
  if(oauthError) return NextResponse.redirect(new URL("/dashboard?error=youtube_denied",request.url));
  if(!code || !state || state!==expectedState) return NextResponse.redirect(new URL("/dashboard?error=youtube_state",request.url));

  const clientId=process.env.GOOGLE_CLIENT_ID;
  const clientSecret=process.env.GOOGLE_CLIENT_SECRET;
  if(!clientId || !clientSecret) return NextResponse.redirect(new URL("/dashboard?error=youtube_config",request.url));

  const redirectUri=process.env.YOUTUBE_REDIRECT_URI || `${url.origin}/api/youtube/callback`;
  const tokenResponse=await fetch("https://oauth2.googleapis.com/token",{
    method:"POST",
    headers:{"Content-Type":"application/x-www-form-urlencoded"},
    body:new URLSearchParams({
      code,
      client_id:clientId,
      client_secret:clientSecret,
      redirect_uri:redirectUri,
      grant_type:"authorization_code"
    })
  });
  if(!tokenResponse.ok) return NextResponse.redirect(new URL("/dashboard?error=youtube_token",request.url));
  const token=await tokenResponse.json() as TokenResponse;

  const channelResponse=await fetch("https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",{
    headers:{Authorization:`Bearer ${token.access_token}`}
  });
  if(!channelResponse.ok) return NextResponse.redirect(new URL("/dashboard?error=youtube_channel",request.url));
  const channelData=await channelResponse.json() as ChannelResponse;
  const youtubeChannel=channelData.items?.[0];
  if(!youtubeChannel?.id) return NextResponse.redirect(new URL("/dashboard?error=no_youtube_channel",request.url));

  const admin=createSupabaseAdmin(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );

  const {data:existing}=await admin.from("channels")
    .select("id")
    .eq("user_id",user.id)
    .eq("youtube_channel_id",youtubeChannel.id)
    .maybeSingle();

  let channelId=existing?.id as string|undefined;
  if(channelId){
    const {error}=await admin.from("channels").update({
      name:youtubeChannel.snippet?.title || "YouTube Channel",
      status:"inactive"
    }).eq("id",channelId);
    if(error) return NextResponse.redirect(new URL("/dashboard?error=youtube_database",request.url));
  }else{
    const {data:created,error}=await admin.from("channels").insert({
      user_id:user.id,
      name:youtubeChannel.snippet?.title || "YouTube Channel",
      youtube_channel_id:youtubeChannel.id,
      status:"inactive"
    }).select("id").single();
    if(error || !created) return NextResponse.redirect(new URL("/dashboard?error=youtube_database",request.url));
    channelId=created.id;
  }

  const {error:tokenError}=await admin.from("youtube_tokens").upsert({
    channel_id:channelId,
    access_token:token.access_token,
    refresh_token:token.refresh_token || "",
    token_expires_at:new Date(Date.now()+token.expires_in*1000).toISOString(),
    scopes:(token.scope||"").split(" ").filter(Boolean)
  });
  if(tokenError) return NextResponse.redirect(new URL("/dashboard?error=youtube_token_database",request.url));

  const response=NextResponse.redirect(new URL("/dashboard?youtube=connected",request.url));
  response.cookies.delete("youtube_oauth_state");
  return response;
}
