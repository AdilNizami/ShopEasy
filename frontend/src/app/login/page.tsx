"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/components/app-providers";
import { Alert, Button, Field, usePageTitle } from "@/components/ui";

function safeNext(value:string|null){return value&&value.startsWith("/")&&!value.startsWith("//")?value:"/profile";}
export default function LoginPage(){usePageTitle("Sign in");const {login,user,ready}=useAuth();const router=useRouter();const [username,setUsername]=useState("");const [password,setPassword]=useState("");const [error,setError]=useState("");const [busy,setBusy]=useState(false);const [next,setNext]=useState("/profile");
  useEffect(()=>{setNext(safeNext(new URLSearchParams(window.location.search).get("next")));},[]);
  useEffect(()=>{if(ready&&user)router.replace(next);},[ready,user,next,router]);
  const submit=async(e:React.FormEvent)=>{e.preventDefault();setError("");setBusy(true);try{await login(username,password);router.replace(next);}catch(cause){setError(cause instanceof ApiError&&cause.status===401?"That username and password combination doesn’t match. Please try again.":cause instanceof Error?cause.message:"We couldn’t sign you in.");}finally{setBusy(false);}};
  return <section className="container-shop grid min-h-[70vh] items-center gap-10 py-12 md:grid-cols-2"><div className="max-w-lg"><p className="eyebrow text-green-700">Welcome back</p><h1 className="mt-4 font-display text-5xl leading-tight">Good to see you again.</h1><p className="mt-5 text-base leading-7 text-muted">Sign in to pick up where you left off and keep your cart and orders in one place.</p><div className="mt-9 rounded-3xl bg-[#e9eee5] p-7"><p className="font-display text-2xl">Your everyday, a little easier.</p><p className="mt-2 text-sm leading-6 text-muted">Your account keeps your orders private and your shopping details close at hand.</p></div></div><form onSubmit={submit} className="mx-auto w-full max-w-md rounded-3xl border border-line bg-white p-6 shadow-card sm:p-9"><h2 className="font-display text-3xl">Sign in</h2><p className="mb-7 mt-2 text-sm text-muted">Enter the username and password for your ShopEasy account.</p>{error&&<div className="mb-5"><Alert>{error}</Alert></div>}<div className="space-y-5"><Field label="Username" required name="username" autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} minLength={3} maxLength={64} pattern="[A-Za-z0-9_.-]+"/><Field label="Password" required name="password" type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} minLength={12} maxLength={128}/></div><Button type="submit" disabled={busy} className="mt-7 w-full">{busy?"Signing in…":"Sign in"}</Button><p className="mt-6 text-center text-sm text-muted">New to ShopEasy? <Link href={`/register?next=${encodeURIComponent(next)}`} className="font-semibold text-green-700 underline underline-offset-4">Create an account</Link></p></form></section>;
}
