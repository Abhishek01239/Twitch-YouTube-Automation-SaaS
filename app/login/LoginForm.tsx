"use client";

import {useState} from "react";
import {createClient} from "../../lib/supabase/client";

export default function LoginForm(){
 const supabase=createClient();
 const [email,setEmail]=useState("");
 const [password,setPassword]=useState("");
 const [mode,setMode]=useState<"login"|"signup">("login");
 const [message,setMessage]=useState("");

 async function submit(e:React.FormEvent){
  e.preventDefault();
  setMessage("Working...");
  if(mode==="login"){
   const {error}=await supabase.auth.signInWithPassword({email,password});
   if(error){setMessage(error.message);return;}
   window.location.href="/dashboard";
   return;
  }

  const {data,error}=await supabase.auth.signUp({
   email,
   password,
   options:{emailRedirectTo:`${window.location.origin}/auth/callback`}
  });
  if(error){setMessage(error.message);return;}

  if(data.session){
   window.location.href="/dashboard";
  }else{
   setMessage("Account created. Check your email to confirm your account, then sign in.");
  }
 }

 return <form onSubmit={submit} className="mt-6 space-y-4">
  <input required type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="Email" className="w-full rounded-xl border border-zinc-700 bg-zinc-900 px-4 py-3 outline-none"/>
  <input required minLength={6} type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="Password" className="w-full rounded-xl border border-zinc-700 bg-zinc-900 px-4 py-3 outline-none"/>
  <button className="w-full rounded-xl bg-white px-4 py-3 font-semibold text-black">{mode==="login"?"Sign in":"Create account"}</button>
  <button type="button" onClick={()=>{setMode(mode==="login"?"signup":"login");setMessage("");}} className="w-full text-sm text-purple-400">{mode==="login"?"Need an account? Sign up":"Already have an account? Sign in"}</button>
  {message&&<p className="text-sm text-zinc-400">{message}</p>}
 </form>;
}