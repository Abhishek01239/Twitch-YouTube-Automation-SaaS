"use client";

import {useState} from "react";

export default function BillingButton({channelId}:{channelId:string}){
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState("");

  async function subscribe(){
    setLoading(true);
    setError("");
    try{
      const response=await fetch("/api/billing/subscribe",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({channelId})
      });
      const data=await response.json().catch(()=>({}));
      if(!response.ok)throw new Error(data.error||"Unable to start subscription");
      if(!data.shortUrl)throw new Error("Razorpay did not return a checkout URL");
      window.location.assign(data.shortUrl);
    }catch(e){
      setError(e instanceof Error?e.message:"Unable to start subscription");
      setLoading(false);
    }
  }

  return <div className="mt-3">
    <button
      onClick={subscribe}
      disabled={loading}
      className="rounded-lg bg-white px-4 py-2 text-sm font-semibold text-black disabled:opacity-50"
    >
      {loading?"Opening Razorpay…":"Activate ₹99/month"}
    </button>
    {error&&<p className="mt-2 text-xs text-red-400">{error}</p>}
  </div>;
}
