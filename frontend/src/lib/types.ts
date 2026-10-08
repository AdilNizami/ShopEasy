export type Money = { amount: string | number; currency: string };
export type Product = {
  id: string; name: string; description: string; price: Money; sellable: boolean;
  categoryId?: string | null; category?: string | null; imageUrl?: string | null; updatedAt: string;
};
export type Category = { id: string; name: string; slug: string };
export type ProductPage = { items: Product[]; nextCursor: string | null };
export type CartItem = { productId: string; name: string; quantity: number; unitPrice: Money };
export type Cart = { id: string; status: "ACTIVE" | "CHECKING_OUT" | "CHECKED_OUT"; items: CartItem[]; subtotal: Money | null; createdAt: string; updatedAt: string };
export type OrderStatus = "PENDING_PAYMENT" | "PAID" | "PROCESSING" | "SHIPPED" | "DELIVERED" | "CANCELLED";
export type OrderLine = { productId: string; name: string; quantity: number; unitPrice: Money; lineTotal: Money };
export type Order = { id: string; status: OrderStatus; items: OrderLine[]; total: Money; paymentId: string | null; createdAt: string; updatedAt: string };
export type OrderPage = { items: Order[]; nextCursor: string | null };
export type CurrentUser = { userId: string; username: string; role?: "customer" | "operator" };
export type AccessToken = { accessToken: string; tokenType: string; expiresIn: number; userId: string };
export type ApiErrorBody = { error?: { code?: string; message?: string; correlationId?: string; retryable?: boolean } };
