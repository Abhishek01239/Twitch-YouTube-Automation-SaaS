import {NextResponse} from "next/server";
import {createClient} from "@/lib/supabase/server";
import {createClient as createSupabaseAdmin} from "@supabase/supabase-js";

export async function GET(request:Request){
  const url=new URL(request.url);
  const code=url.searchParams.get("code");
  const state=url.searchParams.get("state");
  const error=url.searchParams.get("error");

  const supabase=await createClient();
  const {data:{user}}=await supabase.auth.getUser();
  if(!user) return NextResponse.redirect(new URL("/login",request.url));

  const expectedState=(await import("next/headers")).cookies().then(c=>c.get("twitch_oauth_state")?.value);
  if(error) return NextResponse.redirect(new URL("/dashboard?error=twitch_denied",request.url));
  if(!code || !state || state!==await expectedState){
    return NextResponse.redirect(new URL("/dashboard?error=twitch_state",request.url));
  }

  const clientId=process.env.TWITCH_CLIENT_ID;
  const clientSecret=process.env.TWITCH_CLIENT_SECRET;
  if(!clientId || !clientSecret) return NextResponse.redirect(new URL("/dashboard?error=twitch_config",request.url));

  const redirectUri=process.env.TWITCH_REDIRECT_URI || `${url.origin}/api/twitch/callback`;
  const tokenResponse=await fetch("https://id.twitch.tv/oauth2/token",{
    method:"POST",
    headers:{"Content-Type":"application/x-www-form-urlencoded"},
    body:new URLSearchParams({
      client_id:clientId,
      client_secret:clientSecret,
      code,
      grant_type:"authorization_code",
      redirect_uri:redirectUri
    })
  });
  if(!tokenResponse.ok) return NextResponse.redirect(new URL("/dashboard?error=twitch_token",request.url));

  const token=await tokenResponse.json() as {access_token:string;refresh_token:string;expires_in:number};
  const validateResponse=await fetch("https://id.twitch.tv/oauth2/validate",{
    headers:{Authorization:`OAuth ${token.access_token}`}
  });
  if(!validateResponse.ok) return NextResponse.redirect(new URL("/dashboard?error=twitch_validate",request.url));

  const identity=await validateResponse.json() as {user_id:string;login:string;expires_in:number};
  const usersResponse=await fetch(`https://api.twitch.tv/helix/users?id=${encodeURIComponent(identity.user_id)}`,{
    headers:{
      "Client-Id":clientId,
      Authorization:`Bearer ${token.access_token}`
    }
  });
  if(!usersResponse.ok) return NextResponse.redirect(new URL("/dashboard?error=twitch_user",request.url));

  const users=await usersResponse.json() as {data:Array<{id:string;login:string;display_name:string}>};
  const twitchUser=users.data?.[0];
  if(!twitchUser) return NextResponse.redirect(new URL("/dashboard?error=twitch_user",request.url));

  const admin=createSupabaseAdmin(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  );

  const {error:dbError}=await admin.from("twitch_connections").upsert({
    user_id:user.id,
    twitch_user_id:twitchUser.id,
    twitch_login:twitchUser.login,
    twitch_display_name:twitchUser.display_name,
    twitch_access_token:token.access_token,
    twitch_refresh_token:token.refresh_token,
    twitch_token_expires_at:new Date(Date.now()+token.expires_in*1000).toISOString()
  },{onConflict:"user_id"});

  if(dbError) return NextResponse.redirect(new URL("/dashboard?error=twitch_database",request.url));

  const response=NextResponse.redirect(new URL("/dashboard?twitch=connected",request.url));
  response.cookies.delete("twitch_oauth_state");
  return response;
}
