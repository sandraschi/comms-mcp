import { useEffect, useMemo, useState } from "react";
import { api } from "../App";

interface OutboxItem {
    id: number;
    channel: string;
    chat_id: string;
    text: string;
    status: string;
    created_at: string;
    sent_at: string | null;
    error: string | null;
}

const STATUS_FILTERS = ["", "pending", "sent", "failed"];
const PAGE_SIZE = 20;

export default function Outbox() {
    const [items, setItems] = useState<OutboxItem[]>([]);
    const [filter, setFilter] = useState("");
    const [query, setQuery] = useState("");
    const [sortNewest, setSortNewest] = useState(true);
    const [page, setPage] = useState(0);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const load = async (status: string) => {
        setLoading(true);
        setError(null);
        try {
            const r = await api.get("/v1/outbox", {
                params: { status, limit: 200 },
            });
            setItems(r.data.items);
        } catch (e: unknown) {
            setItems([]);
            setError(e instanceof Error ? e.message : "load failed");
        }
        setLoading(false);
        setPage(0);
    };

    useEffect(() => {
        load(filter);
    }, [filter]);

    const visible = useMemo(() => {
        const q = query.trim().toLowerCase();
        const matched = items.filter(
            (it) =>
                !q ||
                it.text.toLowerCase().includes(q) ||
                it.chat_id.toLowerCase().includes(q) ||
                it.channel.toLowerCase().includes(q),
        );
        const sorted = [...matched].sort((a, b) =>
            sortNewest ? b.id - a.id : a.id - b.id,
        );
        return sorted;
    }, [items, query, sortNewest]);

    const pageCount = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));
    const safePage = Math.min(page, pageCount - 1);
    const pageItems = visible.slice(
        safePage * PAGE_SIZE,
        safePage * PAGE_SIZE + PAGE_SIZE,
    );

    const badge = (s: string) =>
        s === "sent"
            ? "bg-green-500/10 text-green-400"
            : s === "failed"
              ? "bg-red-500/10 text-red-400"
              : "bg-amber-500/10 text-amber-400";

    return (
        <div data-testid="outbox-page">
            <h1 className="text-2xl font-bold">Outbox</h1>
            <p className="mt-1 text-sm text-zinc-300">
                Delivery log for outbound sends (pending / sent / failed).
            </p>
            <div className="mt-4 flex flex-wrap items-center gap-2">
                {STATUS_FILTERS.map((s) => (
                    <button
                        type="button"
                        key={s || "all"}
                        onClick={() => setFilter(s)}
                        data-testid={`outbox-filter-${s || "all"}`}
                        className={`rounded-lg px-3 py-1.5 text-sm border ${
                            filter === s
                                ? "border-amber-500/40 bg-amber-500/10 text-amber-300"
                                : "border-zinc-800 text-zinc-300"
                        }`}
                    >
                        {s || "all"}
                    </button>
                ))}
                <input
                    value={query}
                    onChange={(e) => {
                        setQuery(e.target.value);
                        setPage(0);
                    }}
                    placeholder="search text, chat, channel…"
                    data-testid="outbox-search"
                    className="ml-auto min-w-52 flex-1 rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-100 outline-none focus:border-amber-500/50"
                />
                <button
                    type="button"
                    onClick={() => setSortNewest((v) => !v)}
                    data-testid="outbox-sort"
                    className="rounded-lg border border-zinc-800 px-3 py-1.5 text-sm text-zinc-300"
                >
                    {sortNewest ? "newest first" : "oldest first"}
                </button>
            </div>
            <div
                data-testid="outbox-count"
                className="mt-2 text-sm text-zinc-300"
            >
                {visible.length} items
            </div>
            {error && (
                <div className="mt-2 rounded-xl border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
                    Load failed ({error}){" "}
                    <button
                        type="button"
                        onClick={() => load(filter)}
                        className="underline"
                    >
                        retry
                    </button>
                </div>
            )}
            <div className="mt-4 space-y-2">
                {loading && (
                    <div className="text-sm text-zinc-300">Loading…</div>
                )}
                {!loading && !error && visible.length === 0 && (
                    <div className="rounded-xl border border-dashed border-zinc-800 p-8 text-center text-sm text-zinc-400">
                        {query
                            ? `No outbox items match "${query}"`
                            : "No outbox items"}
                    </div>
                )}
                {pageItems.map((it) => (
                    <div
                        key={it.id}
                        className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4"
                    >
                        <div className="flex items-center gap-3 text-sm text-zinc-400">
                            <span
                                className={`rounded px-2 py-0.5 text-sm font-medium ${badge(it.status)}`}
                            >
                                {it.status}
                            </span>
                            <span>#{it.id}</span>
                            <span className="text-amber-300">{it.channel}</span>
                            <span className="text-amber-300/80">
                                {it.chat_id}
                            </span>
                            <span>
                                {new Date(it.created_at).toLocaleString()}
                            </span>
                            {it.error && (
                                <span className="text-red-300">
                                    ({it.error})
                                </span>
                            )}
                        </div>
                        <div className="mt-1.5 text-sm text-zinc-100">
                            {it.text}
                        </div>
                    </div>
                ))}
            </div>
            {pageCount > 1 && (
                <div className="mt-4 flex items-center gap-2">
                    <button
                        type="button"
                        disabled={safePage === 0}
                        onClick={() => setPage((p) => p - 1)}
                        data-testid="outbox-prev"
                        className="rounded-lg border border-zinc-800 px-3 py-1.5 text-sm text-zinc-300 disabled:opacity-40"
                    >
                        prev
                    </button>
                    <span
                        data-testid="outbox-page-num"
                        className="text-sm text-zinc-300"
                    >
                        page {safePage + 1} / {pageCount}
                    </span>
                    <button
                        type="button"
                        disabled={safePage >= pageCount - 1}
                        onClick={() => setPage((p) => p + 1)}
                        data-testid="outbox-next"
                        className="rounded-lg border border-zinc-800 px-3 py-1.5 text-sm text-zinc-300 disabled:opacity-40"
                    >
                        next
                    </button>
                </div>
            )}
        </div>
    );
}
