import Link from "next/link";
import type { Product } from "@/lib/types";
import { money } from "@/lib/api";
import { ProductImage } from "./ui";

export function ProductCard({ product }: { product: Product }) {
  return <article className="group overflow-hidden rounded-3xl border border-line bg-white transition duration-300 hover:-translate-y-1 hover:shadow-card">
    <Link href={`/products/${product.id}`} className="block">
      <div className="relative aspect-[4/3] overflow-hidden bg-[#e9eee5]"><ProductImage src={product.imageUrl} name={product.name} className="transition duration-500 group-hover:scale-[1.04]"/><span className={`absolute left-4 top-4 rounded-full px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider ${product.sellable ? "bg-white/90 text-green-700" : "bg-white/90 text-muted"}`}>{product.sellable ? "Available" : "Sold out"}</span></div>
      <div className="p-5"><p className="mb-2 text-xs font-medium text-muted">{product.category || "ShopEasy selection"}</p><div className="flex items-start justify-between gap-3"><h3 className="line-clamp-2 font-display text-xl leading-6 text-ink group-hover:text-green-700">{product.name}</h3><span className="shrink-0 text-sm font-semibold">{money(product.price)}</span></div><p className="mt-3 line-clamp-2 text-sm leading-6 text-muted">{product.description}</p><span className="mt-5 flex items-center justify-between border-t border-line pt-4 text-xs font-bold uppercase tracking-wider">Explore product <span aria-hidden="true" className="text-lg transition group-hover:translate-x-1">→</span></span></div>
    </Link>
  </article>;
}
