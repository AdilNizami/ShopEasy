"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { AccessToken, Cart, CurrentUser } from "@/lib/types";

type AuthContextType = { user: CurrentUser | null; ready: boolean; login: (username: string, password: string) => Promise<void>; register: (username: string, password: string) => Promise<void>; logout: () => void; refreshUser: () => Promise<void> };
type CartContextType = { cart: Cart | null; loading: boolean; busy: boolean; error: string | null; refresh: () => Promise<void>; add: (productId: string, quantity?: number) => Promise<void>; setQuantity: (productId: string, quantity: number) => Promise<void>; remove: (productId: string) => Promise<void>; clear: () => void };
const AuthContext = createContext<AuthContextType | null>(null);
const CartContext = createContext<CartContextType | null>(null);

export function AppProviders({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [ready, setReady] = useState(false);
  const [cart, setCart] = useState<Cart | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshUser = useCallback(async () => {
    if (!window.sessionStorage.getItem("shopeasy.accessToken")) { setUser(null); return; }
    try { setUser(await api<CurrentUser>("/auth/me")); }
    catch { window.sessionStorage.removeItem("shopeasy.accessToken"); setUser(null); }
  }, []);

  useEffect(() => {
    void refreshUser().finally(() => setReady(true));
  }, [refreshUser]);

  useEffect(() => {
    const expireSession = () => { setUser(null); setCart(null); };
    window.addEventListener("shopeasy:unauthorized", expireSession);
    return () => window.removeEventListener("shopeasy:unauthorized", expireSession);
  }, []);

  const receiveToken = async (result: AccessToken) => {
    window.sessionStorage.setItem("shopeasy.accessToken", result.accessToken);
    await refreshUser();
  };
  const login = async (username: string, password: string) => receiveToken(await api<AccessToken>("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }));
  const register = async (username: string, password: string) => receiveToken(await api<AccessToken>("/auth/register", { method: "POST", body: JSON.stringify({ username, password }) }));
  const logout = () => { window.sessionStorage.removeItem("shopeasy.accessToken"); setUser(null); setCart(null); };

  const refreshCart = useCallback(async () => {
    if (!user) { setCart(null); return; }
    const cartId = window.localStorage.getItem(`shopeasy.cart.${user.userId}`);
    if (!cartId) { setCart(null); return; }
    setLoading(true); setError(null);
    try { setCart(await api<Cart>(`/carts/${cartId}`)); }
    catch (cause) {
      if (cause instanceof Error && "status" in cause && (cause as { status: number }).status === 404) {
        window.localStorage.removeItem(`shopeasy.cart.${user.userId}`); setCart(null);
      } else setError(cause instanceof Error ? cause.message : "We couldn’t load your cart.");
    } finally { setLoading(false); }
  }, [user]);

  useEffect(() => { void refreshCart(); }, [refreshCart]);
  const getOrCreateCart = async () => {
    if (!user) throw new Error("Sign in to use your cart.");
    const key = `shopeasy.cart.${user.userId}`;
    const known = window.localStorage.getItem(key);
    if (known) {
      try { return await api<Cart>(`/carts/${known}`); }
      catch (cause) {
        if (!(cause instanceof Error && "status" in cause && (cause as { status: number }).status === 404)) throw cause;
        window.localStorage.removeItem(key);
      }
    }
    const created = await api<Cart>("/carts", { method: "POST" });
    window.localStorage.setItem(key, created.id);
    return created;
  };
  const mutate = async (fn: () => Promise<Cart>) => {
    setBusy(true); setError(null);
    try { const next = await fn(); setCart(next); }
    catch (cause) { const message = cause instanceof Error ? cause.message : "We couldn’t update your cart."; setError(message); throw cause; }
    finally { setBusy(false); }
  };
  const add = async (productId: string, quantity = 1) => mutate(async () => {
    const current = await getOrCreateCart();
    return api<Cart>(`/carts/${current.id}/items`, { method: "POST", body: JSON.stringify({ productId, quantity }) });
  });
  const setQuantity = async (productId: string, quantity: number) => {
    if (!cart) throw new Error("Your cart is empty.");
    if (quantity <= 0) return remove(productId);
    const current = cart;
    const previousQuantity = current.items.find(item => item.productId === productId)?.quantity;
    if (!previousQuantity) throw new Error("That item is no longer in your cart.");
    return mutate(async () => {
      try {
        return await api<Cart>(`/carts/${current.id}/items/${productId}`, {
          method: "PUT",
          body: JSON.stringify({ quantity }),
        });
      } catch (cause) {
        try { setCart(await api<Cart>(`/carts/${current.id}`)); } catch { /* retain the original failure */ }
        throw cause;
      }
    });
  };
  const remove = async (productId: string) => {
    if (!cart) return;
    const current = cart;
    return mutate(() => api<Cart>(`/carts/${current.id}/items/${productId}`, { method: "DELETE" }));
  };
  const clear = () => { setCart(null); if (user) window.localStorage.removeItem(`shopeasy.cart.${user.userId}`); };

  const authValue = useMemo(() => ({ user, ready, login, register, logout, refreshUser }), [user, ready, refreshUser]);
  const cartValue = useMemo(() => ({ cart, loading, busy, error, refresh: refreshCart, add, setQuantity, remove, clear }), [cart, loading, busy, error, refreshCart, user]);
  return <AuthContext.Provider value={authValue}><CartContext.Provider value={cartValue}>{children}</CartContext.Provider></AuthContext.Provider>;
}

export function useAuth() { const value = useContext(AuthContext); if (!value) throw new Error("useAuth must be used inside AppProviders"); return value; }
export function useCart() { const value = useContext(CartContext); if (!value) throw new Error("useCart must be used inside AppProviders"); return value; }
