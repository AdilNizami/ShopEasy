"use client";

import Link from "next/link";
import { useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth, useCart } from "./app-providers";

export function SiteHeader() {
  const { user, ready, logout } = useAuth();
  const { cart } = useCart();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const pathname = usePathname();
  const router = useRouter();
  const navItems = [{ label: "Shop", href: "/products" }, { label: "Our approach", href: "/#about" }];
  if (user?.role === "operator") navItems.push({ label: "Engineering", href: "/engineering" });
  const itemCount = cart?.items.reduce((sum, item) => sum + item.quantity, 0) || 0;
  const search = (event: React.FormEvent) => { event.preventDefault(); const value = query.trim(); if (value) router.push(`/products?q=${encodeURIComponent(value)}`); };
  return <header className="sticky top-0 z-40 border-b border-line bg-canvas/95 backdrop-blur">
    <div className="container-shop flex h-[76px] items-center justify-between gap-5">
      <button aria-label={open ? "Close navigation" : "Open navigation"} aria-expanded={open} onClick={() => setOpen(!open)} className="rounded-full p-2 text-ink md:hidden"><svg aria-hidden="true" viewBox="0 0 24 24" className="h-6 w-6" fill="none"><path d={open ? "M6 6l12 12M18 6 6 18" : "M4 7h16M4 12h16M4 17h16"} stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg></button>
      <Link href="/" className="shrink-0 font-display text-2xl font-bold tracking-tight">ShopEasy<span className="text-green-600">.</span></Link>
      <nav aria-label="Main navigation" className="hidden items-center gap-7 md:flex">{navItems.map(item => <Link key={item.href} href={item.href} className={`text-sm font-medium transition hover:text-green-700 ${pathname === item.href ? "text-green-700" : "text-ink"}`}>{item.label}</Link>)}</nav>
      <form onSubmit={search} className="hidden max-w-xs flex-1 items-center rounded-full border border-line bg-white px-4 md:flex" role="search"><svg aria-hidden="true" className="h-4 w-4 shrink-0 text-muted" viewBox="0 0 20 20" fill="none"><circle cx="8.8" cy="8.8" r="5.8" stroke="currentColor" strokeWidth="1.5"/><path d="m13 13 4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search the collection" aria-label="Search products" className="h-10 min-w-0 flex-1 bg-transparent px-3 text-sm outline-none placeholder:text-muted/70"/></form>
      <div className="flex shrink-0 items-center gap-1 sm:gap-3">
        {!ready ? <span className="skeleton hidden h-9 w-20 rounded-full sm:block"/> : user ? <div className="hidden items-center gap-2 sm:flex"><Link href="/profile" className="max-w-28 truncate text-sm font-medium hover:text-green-700">Hi, {user.username}</Link><button onClick={logout} className="text-xs text-muted hover:text-ink">Sign out</button></div> : <Link href="/login" className="hidden rounded-full px-3 py-2 text-sm font-semibold hover:bg-white sm:block">Sign in</Link>}
        <Link href="/cart" aria-label={`Cart${itemCount ? `, ${itemCount} items` : ""}`} className="relative flex h-11 items-center gap-2 rounded-full border border-line bg-white px-4 text-sm font-semibold hover:border-ink"><svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none"><path d="M4 5h2l2.1 10.1a2 2 0 0 0 2 1.6h7.6a2 2 0 0 0 1.9-1.4L21 9H7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/><circle cx="10" cy="20" r="1" fill="currentColor"/><circle cx="18" cy="20" r="1" fill="currentColor"/></svg><span className="hidden sm:inline">Cart</span>{itemCount > 0 && <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-green-700 px-1 text-[10px] text-white">{itemCount}</span>}</Link>
      </div>
    </div>
    {open && <div className="border-t border-line bg-white p-5 md:hidden"><form onSubmit={search} className="mb-4 flex rounded-xl border border-line px-4"><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search products" aria-label="Search products" className="h-11 flex-1 outline-none"/></form><nav className="grid gap-1" aria-label="Mobile navigation">{navItems.map(item => <Link onClick={() => setOpen(false)} key={item.href} href={item.href} className="rounded-xl px-3 py-3 text-sm font-medium hover:bg-canvas">{item.label}</Link>)}<Link onClick={() => setOpen(false)} href={user ? "/profile" : "/login"} className="rounded-xl px-3 py-3 text-sm font-medium hover:bg-canvas">{user ? "My account" : "Sign in"}</Link>{user && <button onClick={() => { logout(); setOpen(false); }} className="rounded-xl px-3 py-3 text-left text-sm text-muted hover:bg-canvas">Sign out</button>}</nav></div>}
  </header>;
}
