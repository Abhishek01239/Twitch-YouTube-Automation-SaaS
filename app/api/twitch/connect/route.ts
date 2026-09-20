import {NextResponse} from "next/server";
import {createClient} from "@/lib/supabase/server";
import {randomUUID} from "crypto";

export async function GET(request:Request){
  const supabase=await createClient();
  const {data:{user}}=await supabase.auth.getUser();
  if(!user) return NextResponse.redirect(new URL("/login",request.url));

  const clientId=process.env.TWITCH_CLIENT_ID;
  if(!clientId) return NextResponse.json({error:"TWITCH_CLIENT_ID is not configured"}, {status:500});

  const url=new URL(request.url);
  const redirectUri=process.env.TWITCH_REDIRECT_URI || `${url.origin}/api/twitch/callback`;
  const state=randomUUID();

  const response=NextResponse.redirect(
    `https://id.twitch.tv/oauth2/authorize?response_type=code&client_id=${encodeURIComponent(clientId)}&redirect_uri=${encodeURIComponent(redirectUri)}&scope=&state=${encodeURIComponent(state)}`
  );

  response.cookies.set("twitch_oauth_state",state,{
    httpOnly:true,
    secure:process.env.NODE_ENV==="production",
    sameSite:"lax",
    maxAge:600,
    path:"/"
  });
  return response;
}
