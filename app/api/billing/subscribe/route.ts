import {NextResponse} from "next/server";
import {createClient} from "../../../../lib/supabase/server";
import {createClient as createSupabaseAdmin} from "@supabase/supabase-js";

const RAZORPAY_BASE="https://api.razorpay.com/v1";

type RazorpaySubscription={
  id:string;
  status:string;
  short_url?:string|null;
  current_end?:number|null;
  plan_id?:string;
};

function getCredentials(){
  const keyId=process.env.RAZORPAY_KEY_ID;
  const keySecret=process.env.RAZORPAY_KEY_SECRET;
  if(!keyId||!keySecret) throw new Error("Razorpay credentials are not configured");
  return {keyId,keySecret};
}

function authHeader(){
  const {keyId,keySecret}=getCredentials();
  return "Basic "+Buffer.from(keyId+":"+keySecret).toString("base64");
}

function adminClient(){
  const url=process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serviceRole=process.env.SUPABASE_SERVICE_ROLE_KEY;
  if(!url||!serviceRole) throw new Error("Supabase server credentials are not configured");
  return createSupabaseAdmin(url,serviceRole,{auth:{persistSession:false,autoRefreshToken:false}});
}

function localStatus(status:string){
  if(status==="active") return "active";
  if(status==="paused"||status==="pending"||status==="halted") return "paused";
  if(status==="cancelled") return "cancelled";
  if(status==="completed"||status==="expired") return "expired";
  return "inactive";
}

async function razorpayRequest(path:string,init:RequestInit={}){
  const response=await fetch(RAZORPAY_BASE+path,{
    ...init,
    headers:{
      Authorization:authHeader(),
      "Content-Type":"application/json",
      ...(init.headers||{})
    },
    cache:"no-store"
  });
  const payload=await response.json().catch(()=>({}));
  return {response,payload};
}

export async function POST(request:Request){
  try{
    const supabase=await createClient();
    const {data:{user}}=await supabase.auth.getUser();
    if(!user) return NextResponse.json({error:"Unauthorized"},{status:401});

    const body=await request.json().catch(()=>null);
    const channelId=body?.channelId;
    if(typeof channelId!=="string"||!channelId) {
      return NextResponse.json({error:"channelId is required"},{status:400});
    }

    const {data:channel,error:channelError}=await supabase
      .from("channels")
      .select("id,name")
      .eq("id",channelId)
      .eq("user_id",user.id)
      .maybeSingle();
    if(channelError||!channel) return NextResponse.json({error:"Channel not found"},{status:404});

    const {data:existing,error:existingError}=await supabase
      .from("subscriptions")
      .select("razorpay_subscription_id,status,current_period_end")
      .eq("channel_id",channel.id)
      .maybeSingle();
    if(existingError) {
      console.error("Subscription lookup failed:",existingError);
      return NextResponse.json({error:"Unable to read subscription status"},{status:500});
    }

    if(existing?.status==="active"){
      if(!existing.current_period_end||new Date(existing.current_period_end)>new Date()){
        return NextResponse.json({error:"This channel already has an active subscription"},{status:409});
      }
    }

    // If a previous checkout was started but not completed, reuse its Razorpay
    // subscription instead of creating duplicate recurring subscriptions.
    if(existing?.razorpay_subscription_id && ["inactive","paused"].includes(existing.status)){
      const {response,payload}=await razorpayRequest("/subscriptions/"+encodeURIComponent(existing.razorpay_subscription_id));
      if(response.ok){
        const remote=payload as RazorpaySubscription;
        const mapped=localStatus(remote.status);
        const currentEnd=remote.current_end?new Date(remote.current_end*1000).toISOString():null;

        if(remote.status==="active"){
          const admin=adminClient();
          await admin.from("subscriptions").update({status:"active",current_period_end:currentEnd}).eq("channel_id",channel.id);
          await admin.from("channels").update({status:"active"}).eq("id",channel.id);
          return NextResponse.json({error:"This channel already has an active subscription"},{status:409});
        }

        if(["created","authenticated","pending"].includes(remote.status) && remote.short_url){
          const admin=adminClient();
          await admin.from("subscriptions").update({status:mapped,current_period_end:currentEnd}).eq("channel_id",channel.id);
          return NextResponse.json({
            subscriptionId:remote.id,
            shortUrl:remote.short_url,
            status:remote.status,
            reused:true
          });
        }
      }
      // A missing/terminal remote subscription can safely be replaced below.
    }

    const planId=process.env.RAZORPAY_PLAN_ID;
    if(!planId){
      return NextResponse.json({
        error:"RAZORPAY_PLAN_ID is not configured. Add the Razorpay ₹99/month plan ID to Vercel Production."
      },{status:500});
    }

    // Validate that the configured Razorpay plan is the expected ₹99/month plan
    // before creating a new recurring subscription.
    const {response:planResponse,payload:planPayload}=await razorpayRequest("/plans/"+encodeURIComponent(planId));
    if(!planResponse.ok){
      console.error("Razorpay plan lookup failed:",{
        status:planResponse.status,
        code:planPayload?.error?.code,
        description:planPayload?.error?.description,
        planId
      });
      return NextResponse.json({
        error:"The configured Razorpay plan could not be found in the current Razorpay mode. Check that RAZORPAY_PLAN_ID belongs to the same Test/Live account as the API keys."
      },{status:502});
    }

    const plan=planPayload as {id:string;active?:boolean;period?:string;interval?:number;item?:{amount?:number;currency?:string}};
    if(plan.active===false||plan.period!=="monthly"||plan.interval!==1||plan.item?.amount!==9900||plan.item?.currency!=="INR"){
      return NextResponse.json({
        error:"RAZORPAY_PLAN_ID is not the expected active ₹99/month INR plan."
      },{status:502});
    }

    const {response,payload}=await razorpayRequest("/subscriptions",{
      method:"POST",
      body:JSON.stringify({
        plan_id:planId,
        // 1,200 monthly cycles = 100 years, within Razorpay's maximum duration.
        total_count:1200,
        quantity:1,
        customer_notify:true,
        notes:{
          channel_id:channel.id,
          user_id:user.id,
          channel_name:channel.name
        }
      })
    });

    if(!response.ok){
      const description=payload?.error?.description||"Razorpay subscription creation failed";
      console.error("Razorpay subscription creation failed:",{
        status:response.status,
        code:payload?.error?.code,
        description,
        keyPrefix:getCredentials().keyId.slice(0,8),
        planId
      });
      return NextResponse.json({error:description},{status:502});
    }

    const created=payload as RazorpaySubscription;
    if(!created.id||!created.short_url){
      console.error("Razorpay returned an incomplete subscription:",payload);
      return NextResponse.json({error:"Razorpay did not return a valid subscription checkout URL."},{status:502});
    }

    const currentEnd=created.current_end?new Date(created.current_end*1000).toISOString():null;
    const admin=adminClient();
    const {error:saveError}=await admin.from("subscriptions").upsert({
      channel_id:channel.id,
      razorpay_subscription_id:created.id,
      status:localStatus(created.status),
      amount_paise:9900,
      current_period_end:currentEnd
    },{onConflict:"channel_id"});

    if(saveError){
      console.error("Failed to save Razorpay subscription locally:",saveError);
      return NextResponse.json({
        error:"Subscription was created at Razorpay but could not be saved locally. Please contact support before retrying."
      },{status:500});
    }

    return NextResponse.json({
      subscriptionId:created.id,
      shortUrl:created.short_url,
      status:created.status
    });
  }catch(error){
    console.error("Billing subscription error:",error);
    return NextResponse.json({
      error:error instanceof Error?error.message:"Unexpected billing error"
    },{status:500});
  }
}
