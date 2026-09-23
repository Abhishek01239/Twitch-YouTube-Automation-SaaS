import crypto from "crypto";
import {NextResponse} from "next/server";
import {createClient} from "@supabase/supabase-js";

function verifySignature(rawBody:string,signature:string,secret:string){
  const expected=crypto.createHmac("sha256",secret).update(rawBody).digest("hex");
  if(signature.length!==expected.length)return false;
  return crypto.timingSafeEqual(Buffer.from(expected,"utf8"),Buffer.from(signature,"utf8"));
}

export async function POST(request:Request){
  const secret=process.env.RAZORPAY_WEBHOOK_SECRET;
  const serviceRole=process.env.SUPABASE_SERVICE_ROLE_KEY;
  const supabaseUrl=process.env.NEXT_PUBLIC_SUPABASE_URL;
  if(!secret||!serviceRole||!supabaseUrl){
    return NextResponse.json({error:"Webhook is not configured"},{status:500});
  }

  const rawBody=await request.text();
  const signature=request.headers.get("x-razorpay-signature")||"";
  if(!signature)return NextResponse.json({error:"Missing signature"},{status:400});

  try{
    if(!verifySignature(rawBody,signature,secret)){
      return NextResponse.json({error:"Invalid signature"},{status:401});
    }
  }catch{
    return NextResponse.json({error:"Invalid signature"},{status:401});
  }

  let event:any;
  try{
    event=JSON.parse(rawBody);
  }catch{
    return NextResponse.json({error:"Invalid JSON"},{status:400});
  }

  const entity=event?.payload?.subscription?.entity;
  const subscriptionId=entity?.id;
  if(!subscriptionId)return NextResponse.json({received:true});

  const statusMap:Record<string,string>={
    "subscription.activated":"active",
    "subscription.charged":"active",
    "subscription.resumed":"active",
    // Pending means Razorpay is having payment trouble; do not continue
    // delivering a paid-only service until the subscription is active again.
    "subscription.pending":"paused",
    "subscription.paused":"paused",
    "subscription.halted":"paused",
    "subscription.cancelled":"cancelled",
    "subscription.completed":"expired"
  };

  const status=statusMap[event?.event];
  if(!status)return NextResponse.json({received:true});

  const admin=createClient(supabaseUrl,serviceRole,{
    auth:{persistSession:false,autoRefreshToken:false}
  });

  const {data:sub,error:subError}=await admin
    .from("subscriptions")
    .select("channel_id")
    .eq("razorpay_subscription_id",subscriptionId)
    .maybeSingle();

  if(subError){
    console.error("Billing webhook subscription lookup failed:",subError);
    return NextResponse.json({error:"Database lookup failed"},{status:500});
  }
  if(!sub)return NextResponse.json({received:true});

  const currentEnd=entity.current_end
    ? new Date(entity.current_end*1000).toISOString()
    : null;

  const {error:updateError}=await admin
    .from("subscriptions")
    .update({status,current_period_end:currentEnd})
    .eq("razorpay_subscription_id",subscriptionId);

  if(updateError){
    console.error("Billing webhook subscription update failed:",updateError);
    return NextResponse.json({error:"Database update failed"},{status:500});
  }

  const channelStatus=status==="active"?"active":status==="paused"?"paused":"inactive";
  const {error:channelError}=await admin
    .from("channels")
    .update({status:channelStatus})
    .eq("id",sub.channel_id);

  if(channelError){
    console.error("Billing webhook channel update failed:",channelError);
    return NextResponse.json({error:"Channel update failed"},{status:500});
  }

  return NextResponse.json({received:true});
}
