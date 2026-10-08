"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Category, Product, ProductPage } from "@/lib/types";
import { Alert, Button, EmptyState, Field, PageHeading, SkeletonCard } from "@/components/ui";
import { ProductCard } from "@/components/product-card";

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [moreLoading, setMoreLoading] = useState(false);
  const load = async (cursor?: string, append = false) => {
    const search = new URLSearchParams({ limit: "20" });
    if (q.trim()) search.set("q", q.trim());
    if (categoryId) search.set("categoryId", categoryId);
    if (minPrice) search.set("minPrice", minPrice);
    if (maxPrice) search.set("maxPrice", maxPrice);
    if (cursor) search.set("cursor", cursor);
    if (append) setMoreLoading(true); else { setLoading(true); setError(""); }
    try { const page = await api<ProductPage>(`/products?${search.toString()}`); setProducts(prev => append ? [...prev, ...page.items] : page.items); setNextCursor(page.nextCursor); }
    catch (e) { setError(e instanceof Error ? e.message : "We couldn’t load the collection."); }
    finally { setLoading(false); setMoreLoading(false); }
  };
  useEffect(() => { const params = new URLSearchParams(window.location.search); setQ(params.get("q") || ""); setCategoryId(params.get("categoryId") || ""); api<Category[]>("/categories").then(setCategories).catch(() => setCategories([])); }, []);
  useEffect(() => { const id = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(id); }, [q, categoryId, minPrice, maxPrice]);
  return <section className="container-shop py-12 sm:py-16"><PageHeading eyebrow="Shop the collection" title="Find your everyday favorite." description="Explore the live ShopEasy catalog. Availability and pricing are kept up to date by our store."/>
    <div className="mb-8 grid gap-4 rounded-3xl border border-line bg-white p-4 sm:grid-cols-2 lg:grid-cols-[1.5fr_1fr_1fr_1fr_auto] lg:items-end"><Field label="Search" value={q} onChange={e=>setQ(e.target.value)} placeholder="Try ‘ceramic’"/><div className="space-y-2"><label htmlFor="category" className="block text-sm font-semibold">Category</label><select id="category" value={categoryId} onChange={e=>setCategoryId(e.target.value)} className="h-12 w-full rounded-xl border border-line bg-white px-4 text-sm"><option value="">All categories</option>{categories.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></div><Field label="Minimum price" type="number" min="0" step="0.01" value={minPrice} onChange={e=>setMinPrice(e.target.value)} placeholder="0"/><Field label="Maximum price" type="number" min="0" step="0.01" value={maxPrice} onChange={e=>setMaxPrice(e.target.value)} placeholder="Any"/><Button variant="outline" onClick={()=>{setQ("");setCategoryId("");setMinPrice("");setMaxPrice("");}}>Clear</Button></div>
    {error ? <Alert>{error} <button onClick={()=>void load()} className="ml-1 font-semibold underline">Try again</button></Alert> : loading ? <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">{Array.from({length:6},(_,i)=><SkeletonCard key={i}/>)}</div> : products.length === 0 ? <EmptyState title="Nothing in this corner just yet" description="Try another search or clear the filters to see everything currently available." action={<Button variant="outline" onClick={()=>{setQ("");setCategoryId("");setMinPrice("");setMaxPrice("");}}>Clear filters</Button>}/> : <><p className="mb-4 text-sm text-muted">{products.length} {products.length===1?"product":"products"} shown{nextCursor ? " · more available" : ""}</p><div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">{products.map(p=><ProductCard key={p.id} product={p}/>)}</div>{nextCursor && <div className="mt-10 text-center"><Button variant="outline" disabled={moreLoading} onClick={()=>void load(nextCursor,true)}>{moreLoading?"Loading…":"Load more"}</Button></div>}</>}
  </section>;
}
