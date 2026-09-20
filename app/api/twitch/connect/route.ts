import {NextResponse} from "next/server";
import {createClient} from "../../../../lib/supabase/server";
import {randomUUID} from "crypto";

export async function GET(request:Request){
  const supabase=await createClient();
  const {data:{user}}=await supabase.auth.getUser();
  if(!user) return NextResponse.redirect(new URL("/login",request.url));

  const clientId=process.env.TWITCH_CLIENT_ID;
  if(!clientId) return NextResponse.json({error:"TWITCH_CLIENT_ID is not configured"},{status:500});

  const url=new URL(request.url);
  const redirectUri=process.env.TWITCH_REDIRECT_URI || `${url.origin}/api/twitch/callback`;
  const state=randomUUID();
  const auth=new URL("https://id.twitch.tv/oauth2/authorize");
  auth.searchParams.set("response_type","code");
  auth.searchParams.set("client_id",clientId);
  auth.searchParams.set("redirect_uri",redirectUri);
  auth.searchParams.set("scope","channel:manage:clips");
  auth.searchParams.set("state",state);

  const response=NextResponse.redirect(auth);
  response.cookies.set("twitch_oauth_state",state,{
    httpOnly:true,secure:process.env.NODE_ENV==="production",sameSite:"lax",maxAge:600,path:"/"
  });
  return response;
}
