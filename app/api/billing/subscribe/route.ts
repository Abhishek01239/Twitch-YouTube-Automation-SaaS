import {NextResponse} from "next/server";
import {createClient} from "../../../../lib/supabase/server";

const RAZORPAY_BASE="https://api.razorpay.com/v1";

function authHeader(){
  const keyId=process.env.RAZORPAY_KEY_ID;
  const keySecret=process.env.RAZORPAY_KEY_SECRET;
  if(!keyId||!keySecret) throw new Error("Razorpay credentials are not configured");
  return "Basic "+Buffer.from(keyId+":"+keySecret).toString("base64");
}

export async function POST(request:Request){
  try{
    const supabase=await createClient();
    const {data:{user}}=await supabase.auth.getUser();
    if(!user) return NextResponse.json({error:"Unauthorized"},{status:401});

    const {channelId}=await request.json();
    if(typeof channelId!=="string") return NextResponse.json({error:"channelId is required"},{status:400});

    const {data:channel,error:channelError}=await supabase
      .from("channels").select("id,name").eq("id",channelId).eq("user_id",user.id).maybeSingle();
    if(channelError||!channel) return NextResponse.json({error:"Channel not found"},{status:404});

    const {data:existing}=await supabase.from("subscriptions")
      .select("razorpay_subscription_id,status,current_period_end")
      .eq("channel_id",channel.id).maybeSingle();

    if(existing?.status==="active" && existing.current_period_end && new Date(existing.current_period_end)>new Date()){
      return NextResponse.json({error:"This channel already has an active subscription"},{status:409});
    }

    const planId=process.env.RAZORPAY_PLAN_ID;
    if(!planId) return NextResponse.json({error:"RAZORPAY_PLAN_ID is not configured. Create the ₹99/month plan in Razorpay and add its plan ID as a GitHub/Vercel secret."},{status:500});

    const response=await fetch(RAZORPAY_BASE+"/subscriptions",{
      method:"POST",
      headers:{"Authorization":authHeader(),"Content-Type":"application/json"},
      body:JSON.stringify({
        plan_id:planId,
        total_count:120,
        quantity:1,
        customer_notify:1,
        notes:{channel_id:channel.id,user_id:user.id,channel_name:channel.name}
      })
    });

    const payload=await response.json();
    if(!response.ok){
      return NextResponse.json({error:payload?.error?.description||"Razorpay subscription creation failed"},{status:502});
    }

    const currentEnd=payload.current_end ? new Date(payload.current_end*1000).toISOString() : null;
    const {error:saveError}=await supabase.from("subscriptions").upsert({
      channel_id:channel.id,
      razorpay_subscription_id:payload.id,
      status:payload.status==="active"?"active":"inactive",
      amount_paise:9900,
      current_period_end:currentEnd
    },{onConflict:"channel_id"});

    if(saveError) return NextResponse.json({error:"Subscription was created at Razorpay but could not be saved locally. Contact support."},{status:500});

    return NextResponse.json({subscriptionId:payload.id,shortUrl:payload.short_url,status:payload.status});
  }catch(error){
    return NextResponse.json({error:error instanceof Error?error.message:"Unexpected error"},{status:500});
  }
}
