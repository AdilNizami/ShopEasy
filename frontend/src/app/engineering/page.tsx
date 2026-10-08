"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, formatDate } from "@/lib/api";
import { useAuth } from "@/components/app-providers";
import { Alert, Button, PageHeading } from "@/components/ui";

type ServiceHealth = { name: string; status: "healthy" | "unhealthy"; latencyMs: number | null };
type OutboxEvent = { eventId: string; eventType: string; version: number; occurredAt: string; producer: string; status: string; correlationId: string | null; retryCount: number; lastAttemptAt: string | null; nextAttemptAt: string | null; lastError: string | null };
type ProcessedEvent = { eventId: string; eventType: string; producer: string; timestamp: string; correlationId?: string | null; processingStatus: string; retryCount: number | null };
type ServiceSnapshot = { service: string; outboxPendingCount: number; outboxFailureCount: number; eventsProcessedCount: number; outboxEvents: OutboxEvent[]; processedEvents: ProcessedEvent[] };
type DlqItem = { queue: string; eventId?: string | null; eventType?: string; producer?: string; occurredAt?: string; correlationId?: string; retryCount: number; failureCategory?: string; failedAt?: string };
type DlqQueue = { queue: string; count: number | null; status: "available" | "unavailable"; items: DlqItem[] };

function StatCard({ label, value, note, tone = "green" }: { label: string; value: string | number; note: string; tone?: "green" | "red" | "amber" | "ink" }) {
  const accents = { green: "bg-green-100 text-green-800", red: "bg-red-100 text-red-800", amber: "bg-amber-100 text-amber-900", ink: "bg-ink text-white" };
  return <article className="rounded-3xl border border-line bg-white p-5 shadow-card sm:p-6"><div className="flex items-center justify-between gap-3"><p className="text-sm font-semibold text-muted">{label}</p><span className={`h-2.5 w-2.5 rounded-full ${tone === "red" ? "bg-red-500" : tone === "amber" ? "bg-amber-500" : tone === "ink" ? "bg-ink" : "bg-green-600"}`}/></div><p className={`mt-4 inline-flex rounded-2xl px-3 py-1 font-display text-3xl ${accents[tone]}`}>{value}</p><p className="mt-3 text-xs leading-5 text-muted">{note}</p></article>;
}

function accessMessage(userRole?: string, ready?: boolean) {
  if (!ready) return <div className="container-shop py-16"><div className="skeleton h-72 w-full"/></div>;
  if (!userRole) return <section className="container-shop max-w-2xl py-16"><div className="rounded-3xl border border-line bg-white p-8"><p className="eyebrow text-green-700">Internal dashboard</p><h1 className="mt-3 font-display text-3xl">Operator sign-in required</h1><p className="mt-3 text-sm leading-6 text-muted">This architecture view is available to configured ShopEasy operators only.</p><Link href={`/login?next=${encodeURIComponent("/engineering")}`} className="mt-6 inline-flex min-h-11 items-center rounded-full bg-ink px-5 text-sm font-semibold text-white">Sign in</Link></div></section>;
  if (userRole !== "operator") return <section className="container-shop max-w-2xl py-16"><Alert>Engineering telemetry is restricted to operator accounts. Your customer account cannot view internal service or message data.</Alert><Link href="/" className="mt-5 inline-flex text-sm font-semibold underline">Return to ShopEasy</Link></section>;
  return null;
}

function EngineeringDashboard() {
  const [services, setServices] = useState<ServiceHealth[]>([]);
  const [snapshots, setSnapshots] = useState<ServiceSnapshot[]>([]);
  const [queues, setQueues] = useState<DlqQueue[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [healthUnavailable, setHealthUnavailable] = useState(false);
  const [eventSourcesUnavailable, setEventSourcesUnavailable] = useState(false);
  const [dlqSourceUnavailable, setDlqSourceUnavailable] = useState(false);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    const results = await Promise.allSettled([
      api<{ items: ServiceHealth[] }>("/internal/observability/services"),
      api<ServiceSnapshot>("/internal/observability/service/orders"),
      api<ServiceSnapshot>("/internal/observability/service/payments"),
      api<ServiceSnapshot>("/internal/observability/service/notifications"),
      api<{ queues: DlqQueue[] }>("/internal/observability/dlq"),
    ]);
    const failures: string[] = [];
    if (results[0].status === "fulfilled") { setServices(results[0].value.items); setHealthUnavailable(false); }
    else { failures.push("service health"); setHealthUnavailable(true); }
    const nextSnapshots = results.slice(1, 4).flatMap(result => {
      if (result.status === "fulfilled") return [result.value as ServiceSnapshot];
      failures.push("event and outbox data");
      return [];
    });
    setEventSourcesUnavailable(results.slice(1, 4).some(result => result.status === "rejected"));
    setSnapshots(nextSnapshots);
    const dlqResult = results[4];
    if (dlqResult.status === "fulfilled") { setQueues(dlqResult.value.queues); setDlqSourceUnavailable(false); }
    else { failures.push("dead-letter queues"); setDlqSourceUnavailable(true); }
    setError(failures.length ? `Some live sources could not be reached: ${[...new Set(failures)].join(", ")}.` : "");
    setUpdatedAt(new Date().toISOString());
    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => {
    void refresh();
    const interval = window.setInterval(() => void refresh(), 10_000);
    return () => window.clearInterval(interval);
  }, [refresh]);

  const healthCounts = useMemo(() => ({ healthy: services.filter(service => service.status === "healthy").length, total: services.length }), [services]);
  const processedCount = snapshots.reduce((sum, snapshot) => sum + snapshot.eventsProcessedCount, 0);
  const pendingOutbox = snapshots.reduce((sum, snapshot) => sum + snapshot.outboxPendingCount, 0);
  const dlqCount = queues.reduce((sum, queue) => sum + (queue.count || 0), 0);
  const failedPublishes = snapshots.reduce((sum, snapshot) => sum + snapshot.outboxFailureCount, 0);
  const failedEvents = dlqCount + failedPublishes;
  const dlqUnavailable = dlqSourceUnavailable || queues.some(queue => queue.status !== "available");
  const events = useMemo(() => {
    const outbox = snapshots.flatMap(snapshot => snapshot.outboxEvents);
    const handled = snapshots.flatMap(snapshot => snapshot.processedEvents);
    const handledById = new Map<string, ProcessedEvent>();
    for (const event of handled) {
      const previous = handledById.get(event.eventId);
      handledById.set(event.eventId, previous ? { ...previous, ...event, correlationId: event.correlationId || previous.correlationId } : event);
    }
    const produced = outbox.map(event => {
      const receipt = handledById.get(event.eventId);
      return {
        eventId: event.eventId,
        eventType: event.eventType,
        producer: event.producer,
        timestamp: event.occurredAt,
        correlationId: event.correlationId || receipt?.correlationId || null,
        retryCount: event.retryCount,
        processingStatus: receipt ? "CONSUMED" : event.status === "PENDING" ? "PENDING PUBLISH" : "PUBLISHED",
      };
    });
    const consumedOnly = [...handledById.values()].filter(event => !outbox.some(producedEvent => producedEvent.eventId === event.eventId));
    return [...produced, ...consumedOnly].sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp)).slice(0, 40);
  }, [snapshots]);

  if (loading) return <section className="container-shop py-12"><div className="skeleton mb-8 h-12 w-72"/><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">{[1,2,3,4,5].map(item => <div key={item} className="skeleton h-36"/>)}</div><div className="skeleton mt-8 h-96"/></section>;

  return <section className="container-shop py-10 sm:py-14">
    <PageHeading eyebrow="Internal · event-driven architecture" title="ShopEasy engineering view." description="A read-only view of live service health, transactional outboxes, consumer processing, and RabbitMQ dead-letter queues." action={<Button variant="outline" disabled={refreshing} onClick={() => void refresh()}>{refreshing ? "Refreshing…" : "Refresh data"}</Button>}/>
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-white px-4 py-3 text-xs text-muted"><span>Live sources refresh every 10 seconds.</span><span>{updatedAt ? `Last updated ${formatDate(updatedAt)}` : "Waiting for telemetry"}</span></div>
    {error && <div className="mb-6"><Alert>{error} The cards and tables below show the latest successfully retrieved records.</Alert></div>}
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
      <StatCard label="Services healthy" value={healthUnavailable ? "—" : `${healthCounts.healthy}/${healthCounts.total}`} note="Readiness checks across APIs, gateway, and RabbitMQ." tone={healthUnavailable || (healthCounts.total > 0 && healthCounts.healthy < healthCounts.total) ? "red" : "green"}/>
      <StatCard label="Events processed" value={eventSourcesUnavailable ? "—" : processedCount} note={eventSourcesUnavailable ? "At least one consumer telemetry source is unavailable." : "Committed consumer receipts across Orders and Notifications."} tone="ink"/>
      <StatCard label="Failed events" value={dlqUnavailable || eventSourcesUnavailable ? "—" : failedEvents} note={dlqUnavailable || eventSourcesUnavailable ? "A DLQ or outbox source is unavailable." : `${dlqCount} in DLQ · ${failedPublishes} outbox publish failures awaiting retry.`} tone={failedEvents ? "red" : dlqUnavailable || eventSourcesUnavailable ? "amber" : "green"}/>
      <StatCard label="Outbox pending" value={eventSourcesUnavailable ? "—" : pendingOutbox} note={eventSourcesUnavailable ? "At least one outbox source is unavailable." : "Committed events not yet confirmed as published."} tone={pendingOutbox ? "amber" : eventSourcesUnavailable ? "amber" : "green"}/>
      <StatCard label="DLQ count" value={dlqUnavailable ? "—" : dlqCount} note="RabbitMQ messages retained for operator investigation." tone={dlqCount ? "red" : dlqUnavailable ? "amber" : "green"}/>
    </div>

    <section className="mt-10" aria-labelledby="service-health-title"><div className="mb-4 flex items-end justify-between"><div><p className="eyebrow text-green-700">Runtime</p><h2 id="service-health-title" className="mt-2 font-display text-3xl">Service health</h2></div><span className="text-xs text-muted">Readiness checks include the service’s own database</span></div><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{services.map(service => <article key={service.name} className="flex items-center justify-between gap-4 rounded-2xl border border-line bg-white p-4"><div className="flex min-w-0 items-center gap-3"><span className={`h-3 w-3 shrink-0 rounded-full ${service.status === "healthy" ? "bg-green-600" : "bg-red-500"}`}/><div><h3 className="font-semibold capitalize">{service.name}</h3><p className={`mt-1 text-xs font-medium ${service.status === "healthy" ? "text-green-700" : "text-red-700"}`}>{service.status}</p></div></div><span className="shrink-0 text-xs text-muted">{service.latencyMs === null ? "—" : `${service.latencyMs} ms`}</span></article>)}{services.length === 0 && <p className="rounded-2xl border border-dashed border-line p-6 text-sm text-muted">No service health data is available yet.</p>}</div></section>

    <section className="mt-10" aria-labelledby="events-title"><div className="mb-4"><p className="eyebrow text-green-700">Event stream</p><h2 id="events-title" className="mt-2 font-display text-3xl">Recent events</h2><p className="mt-2 text-sm text-muted">Produced events are matched to durable consumer receipts by eventId. Sensitive event payloads are not shown.</p></div><div className="overflow-hidden rounded-3xl border border-line bg-white"><div className="overflow-x-auto"><table className="w-full min-w-[1050px] border-collapse text-left text-sm"><thead className="bg-[#f1f4ef] text-[10px] uppercase tracking-wider text-muted"><tr>{["Event type","eventId","Producer","Timestamp","Processing status","Correlation ID","Retries"].map(label=><th key={label} scope="col" className="px-4 py-4 font-bold">{label}</th>)}</tr></thead><tbody className="divide-y divide-line">{events.map(event=><tr key={`${event.eventId}-${event.producer}`} className="align-top"><td className="px-4 py-4 font-semibold">{event.eventType}</td><td className="px-4 py-4 font-mono text-xs">{event.eventId}</td><td className="px-4 py-4">{event.producer}</td><td className="px-4 py-4 text-xs text-muted">{formatDate(event.timestamp)}</td><td className="px-4 py-4"><span className={`rounded-full px-2.5 py-1 text-[10px] font-bold ${event.processingStatus === "CONSUMED" ? "bg-green-50 text-green-800" : event.processingStatus === "PENDING PUBLISH" ? "bg-amber-50 text-amber-900" : "bg-blue-50 text-blue-800"}`}>{event.processingStatus}</span></td><td className="px-4 py-4 font-mono text-xs">{event.correlationId || "—"}</td><td className="px-4 py-4">{event.retryCount ?? "—"}</td></tr>)}{events.length === 0 && <tr><td colSpan={7} className="px-5 py-12 text-center text-sm text-muted">No event records are available yet. A successful checkout will populate these tables.</td></tr>}</tbody></table></div></div></section>

    <section className="mt-10" aria-labelledby="outbox-title"><div className="mb-4"><p className="eyebrow text-green-700">Reliable publishing</p><h2 id="outbox-title" className="mt-2 font-display text-3xl">Transactional outbox</h2><p className="mt-2 text-sm text-muted">Outbox records stay with their producing service; pending records remain durable until the RabbitMQ relay succeeds.</p></div><div className="grid gap-4 md:grid-cols-2">{snapshots.filter(snapshot => snapshot.outboxEvents.length || snapshot.service === "orders" || snapshot.service === "payments").map(snapshot=><article key={snapshot.service} className="rounded-3xl border border-line bg-white p-5"><div className="flex items-center justify-between"><h3 className="font-display text-2xl capitalize">{snapshot.service}</h3><span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-900">{snapshot.outboxPendingCount} pending</span></div><div className="mt-4 space-y-3">{snapshot.outboxEvents.slice(0,5).map(event=><div key={event.eventId} className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3 text-xs"><span><strong className="font-semibold">{event.eventType}</strong><span className="ml-2 font-mono text-muted">{event.eventId.slice(0,12)}…</span></span><span className="text-muted">{event.status} · {event.retryCount} publish attempts</span>{event.nextAttemptAt&&<span className="w-full text-muted">Next attempt after {formatDate(event.nextAttemptAt)}</span>}{event.lastError&&<span className="w-full text-red-700">Last error: {event.lastError}</span>}</div>)}{snapshot.outboxEvents.length===0&&<p className="border-t border-line pt-3 text-sm text-muted">No outgoing event records yet.</p>}</div></article>)}</div></section>

    <section className="mt-10" aria-labelledby="dlq-title"><div className="mb-4"><p className="eyebrow text-red-700">Needs attention</p><h2 id="dlq-title" className="mt-2 font-display text-3xl">Dead-letter queues</h2><p className="mt-2 text-sm text-muted">Failed messages are inspected without acknowledging them; this dashboard has no replay, purge, or queue-control actions.</p></div><div className="grid gap-4 md:grid-cols-2">{queues.map(queue=><article key={queue.queue} className="rounded-3xl border border-line bg-white p-5"><div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-mono text-sm">{queue.queue}</h3><span className={`rounded-full px-3 py-1 text-xs font-bold ${queue.status === "available" ? queue.count ? "bg-red-50 text-red-800" : "bg-green-50 text-green-800" : "bg-amber-50 text-amber-900"}`}>{queue.status === "available" ? `${queue.count} messages` : "unavailable"}</span></div>{queue.items.length ? <div className="mt-4 space-y-3">{queue.items.map((item,index)=><div key={`${item.eventId||"unknown"}-${index}`} className="rounded-2xl bg-[#fbf4f2] p-4 text-xs"><p className="font-semibold">{item.eventType || "Unknown event"} <span className="font-normal text-muted">· {item.failureCategory || "consumer failure"}</span></p><p className="mt-2 break-all font-mono text-muted">{item.eventId || "Event ID unavailable"}</p><div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-muted"><span>Producer: {item.producer || "unknown"}</span><span>Retries: {item.retryCount}</span><span>Correlation: {item.correlationId || "—"}</span></div><p className="mt-2 text-muted">Failed {item.failedAt ? formatDate(item.failedAt) : "timestamp unavailable"}</p></div>)}</div> : <p className="mt-4 text-sm text-muted">{queue.status === "available" ? "No DLQ messages currently waiting." : "RabbitMQ management telemetry is unavailable."}</p>}</article>)}{queues.length===0&&<p className="rounded-2xl border border-dashed border-line p-6 text-sm text-muted">No DLQ telemetry is available.</p>}</div></section>
    <p className="mt-10 text-xs leading-5 text-muted">This dashboard is a presentation and inspection surface. It does not provide customer operations or mutate order, payment, inventory, outbox, or queue state.</p>
  </section>;
}

export default function EngineeringPage() {
  const { user, ready } = useAuth();
  const gate = accessMessage(user?.role, ready);
  if (gate) return gate;
  return <EngineeringDashboard/>;
}
