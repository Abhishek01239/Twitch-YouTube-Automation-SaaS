import {NextResponse} from "next/server";
import {createClient} from "../../../../lib/supabase/server";
import {randomUUID} from "crypto";

const scope=[
  "https://www.googleapis.com/auth/youtube.upload",
  "https://www.googleapis.com/auth/youtube.readonly"
].join(" ");

export async function GET(request:Request){
  const supabase=await createClient();
  const {data:{user}}=await supabase.auth.getUser();
  if(!user) return NextResponse.redirect(new URL("/login",request.url));

  const clientId=process.env.GOOGLE_CLIENT_ID;
  if(!clientId) return NextResponse.json({error:"GOOGLE_CLIENT_ID is not configured"},{status:500});

  const url=new URL(request.url);
  const redirectUri=process.env.YOUTUBE_REDIRECT_URI || `${url.origin}/api/youtube/callback`;
  const state=randomUUID();

  const auth=new URL("https://accounts.google.com/o/oauth2/v2/auth");
  auth.searchParams.set("client_id",clientId);
  auth.searchParams.set("redirect_uri",redirectUri);
  auth.searchParams.set("response_type","code");
  auth.searchParams.set("scope",scope);
  auth.searchParams.set("access_type","offline");
  auth.searchParams.set("include_granted_scopes","true");
  auth.searchParams.set("prompt","consent");
  auth.searchParams.set("state",state);

  const response=NextResponse.redirect(auth);
  response.cookies.set("youtube_oauth_state",state,{
    httpOnly:true,
    secure:process.env.NODE_ENV==="production",
    sameSite:"lax",
    maxAge:600,
    path:"/"
  });
  return response;
}
