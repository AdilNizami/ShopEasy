"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "./app-providers";

export function Button({ children, className = "", variant = "dark", disabled, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "dark" | "light" | "outline" | "text" }) {
  const base = "inline-flex min-h-12 items-center justify-center gap-2 rounded-full px-6 text-sm font-semibold transition duration-200 disabled:cursor-not-allowed disabled:opacity-50";
  const variants = {
    dark: "bg-ink text-white hover:bg-green-700",
    light: "bg-citrus text-ink hover:bg-[#c9e252]",
    outline: "border border-line bg-white text-ink hover:border-ink",
    text: "text-ink hover:bg-green-50",
  };
  return <button className={`${base} ${variants[variant]} ${className}`} disabled={disabled} {...props}>{children}</button>;
}

export function Arrow({ direction = "right" }: { direction?: "right" | "left" }) {
  return <svg aria-hidden="true" className={`h-4 w-4 ${direction === "left" ? "rotate-180" : ""}`} viewBox="0 0 20 20" fill="none"><path d="M3.5 10h12m0 0-5-5m5 5-5 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

export function Alert({ children, kind = "error" }: { children: React.ReactNode; kind?: "error" | "success" | "info" }) {
  const style = { error: "border-red-200 bg-red-50 text-red-800", success: "border-green-200 bg-green-50 text-green-800", info: "border-blue-200 bg-blue-50 text-blue-900" }[kind];
  return <div role={kind === "error" ? "alert" : "status"} className={`rounded-2xl border px-4 py-3 text-sm leading-6 ${style}`}>{children}</div>;
}

export function Field({ label, hint, error, ...props }: React.InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string; error?: string }) {
  const id = props.id || props.name || label.toLowerCase().replace(/\s+/g, "-");
  return <div className="space-y-2"><label htmlFor={id} className="block text-sm font-semibold text-ink">{label}{props.required && <span aria-hidden="true" className="text-green-700"> *</span>}</label><input {...props} id={id} aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined} className={`min-h-12 w-full rounded-xl border bg-white px-4 text-sm text-ink placeholder:text-muted/70 ${error ? "border-red-400" : "border-line"} ${props.className || ""}`} />{error ? <p id={`${id}-error`} className="text-sm text-red-700">{error}</p> : hint ? <p id={`${id}-hint`} className="text-xs text-muted">{hint}</p> : null}</div>;
}

export function PageHeading({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: React.ReactNode }) {
  return <div className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">{<div className="max-w-2xl">{eyebrow && <p className="eyebrow mb-3 text-green-700">{eyebrow}</p>}<h1 className="font-display text-4xl tracking-tight text-ink sm:text-5xl">{title}</h1>{description && <p className="mt-3 max-w-xl text-base leading-7 text-muted">{description}</p>}</div>}{action}</div>;
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: React.ReactNode }) {
  return <div className="rounded-3xl border border-dashed border-[#cad2c9] bg-white/70 px-6 py-14 text-center"><span className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-full bg-green-50 text-green-700"><svg aria-hidden="true" viewBox="0 0 24 24" className="h-6 w-6" fill="none"><path d="M4 7h16l-1.3 12H5.3L4 7Zm4 0a4 4 0 0 1 8 0" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg></span><h2 className="font-display text-2xl text-ink">{title}</h2><p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted">{description}</p>{action && <div className="mt-6">{action}</div>}</div>;
}

export function ProductImage({ src, name, className = "" }: { src?: string | null; name: string; className?: string }) {
  const [failed, setFailed] = useState(false);
  if (src && !failed) return <img src={src} alt={name} onError={() => setFailed(true)} className={`h-full w-full object-cover ${className}`} />;
  return <div role="img" aria-label={`${name}: image unavailable`} className={`flex h-full w-full items-center justify-center bg-[radial-gradient(circle_at_30%_25%,#eef3df,transparent_45%),linear-gradient(145deg,#e9eee5,#dce4dc)] ${className}`}><svg aria-hidden="true" viewBox="0 0 120 100" className="h-1/2 max-h-32 text-green-700/50" fill="none"><path d="m60 15 37 20v34L60 89 23 69V35l37-20Z" stroke="currentColor" strokeWidth="2"/><path d="m23 35 37 21 37-21M60 56v33M42 25l37 20" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"/><circle cx="60" cy="56" r="5" fill="currentColor"/></svg></div>;
}

export function SkeletonCard() { return <div className="overflow-hidden rounded-3xl border border-line bg-white"><div className="skeleton aspect-[4/3] rounded-none" /><div className="space-y-3 p-5"><div className="skeleton h-3 w-20"/><div className="skeleton h-5 w-3/4"/><div className="skeleton h-4 w-1/3"/></div></div>; }

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, ready } = useAuth();
  if (!ready) return <div className="container-shop py-20"><div className="skeleton h-64 w-full"/></div>;
  if (!user) return <div className="container-shop py-20"><EmptyState title="Sign in to continue" description="Your cart and order history are private to your account. Sign in or create an account to continue." action={<Link href={`/login?next=${encodeURIComponent(typeof window === "undefined" ? "/" : window.location.pathname)}`} className="inline-flex min-h-12 items-center rounded-full bg-ink px-6 text-sm font-semibold text-white">Sign in</Link>} /></div>;
  return <>{children}</>;
}

export function usePageTitle(title: string) {
  useEffect(() => { document.title = `${title} | ShopEasy`; }, [title]);
}
