import { Inbox as InboxIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../App";

interface InboundItem {
    id: number;
    channel: string;
    chat_id: string;
    sender: string;
    text: string;
    received_at: string;
}

const PAGE_SIZE = 20;

export default function Inbox() {
    const [items, setItems] = useState<InboundItem[]>([]);
    const [query, setQuery] = useState("");
    const [channel, setChannel] = useState("");
    const [newest, setNewest] = useState(true);
    const [page, setPage] = useState(0);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const load = async () => {
        setLoading(true);
        setError(null);
        try {
            const r = await api.get("/v1/inbound", { params: { limit: 200 } });
            setItems(r.data.messages);
        } catch (e: unknown) {
            setItems([]);
            setError(e instanceof Error ? e.message : "load failed");
        }
        setLoading(false);
        setPage(0);
    };

    useEffect(() => {
        void load();
    }, []);

    const channels = useMemo(
        () => Array.from(new Set(items.map((i) => i.channel))),
        [items],
    );
    const visible = useMemo(() => {
        const q = query.trim().toLowerCase();
        const filtered = items.filter(
            (i) =>
                (!channel || i.channel === channel) &&
                (!q ||
                    i.text.toLowerCase().includes(q) ||
                    i.sender.toLowerCase().includes(q) ||
                    i.chat_id.toLowerCase().includes(q)),
        );
        return [...filtered].sort((a, b) =>
            newest ? b.id - a.id : a.id - b.id,
        );
    }, [items, query, channel, newest]);
    const pageCount = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));
    const safePage = Math.min(page, pageCount - 1);
    const pageItems = visible.slice(
        safePage * PAGE_SIZE,
        safePage * PAGE_SIZE + PAGE_SIZE,
    );

    return (
        <div data-testid="inbox-page">
            <h1 className="flex items-center gap-2 text-2xl font-bold">
                <InboxIcon className="h-5 w-5 text-amber-400" /> Inbox
            </h1>
            <p className="mt-1 text-sm text-zinc-300">
                Sanitized inbound messages. Bodies expire after the retention
                window.
            </p>
            <div className="mt-4 flex flex-wrap items-center gap-2">
                <select
                    value={channel}
                    onChange={(e) => {
                        setChannel(e.target.value);
                        setPage(0);
                    }}
                    data-testid="inbox-channel-filter"
                    className="rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-sm text-zinc-100"
                >
                    <option value="">all channels</option>
                    {channels.map((c) => (
                        <option key={c} value={c}>
                            {c}
                        </option>
                    ))}
                </select>
                <input
                    value={query}
                    onChange={(e) => {
                        setQuery(e.target.value);
                        setPage(0);
                    }}
                    placeholder="search text, sender, chat…"
                    data-testid="inbox-search"
                    className="min-w-52 flex-1 rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-100 outline-none focus:border-amber-500/50"
                />
                <button
                    type="button"
                    onClick={() => setNewest((v) => !v)}
                    data-testid="inbox-sort"
                    className="rounded-lg border border-zinc-800 px-3 py-1.5 text-sm text-zinc-300"
                >
                    {newest ? "newest first" : "oldest first"}
                </button>
            </div>
            <div
                data-testid="inbox-count"
                className="mt-2 text-sm text-zinc-300"
            >
                {visible.length} of {items.length}
            </div>
            {error && (
                <div className="mt-2 rounded-xl border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
                    Load failed ({error}){" "}
                    <button
                        type="button"
                        onClick={() => void load()}
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
                        No inbound messages
                    </div>
                )}
                {pageItems.map((it) => (
                    <div
                        key={it.id}
                        className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4"
                    >
                        <div className="flex items-center gap-3 text-sm text-zinc-400">
                            <span className="rounded bg-amber-500/10 px-2 py-0.5 text-amber-300">
                                {it.channel}
                            </span>
                            <span className="text-amber-300/80">
                                {it.sender || it.chat_id}
                            </span>
                            <span>
                                {new Date(it.received_at).toLocaleString()}
                            </span>
                        </div>
                        <div className="mt-1.5 whitespace-pre-wrap text-sm text-zinc-100">
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
                        data-testid="inbox-prev"
                        className="rounded-lg border border-zinc-800 px-3 py-1.5 text-sm text-zinc-300 disabled:opacity-40"
                    >
                        prev
                    </button>
                    <span
                        data-testid="inbox-page-num"
                        className="text-sm text-zinc-300"
                    >
                        page {safePage + 1} / {pageCount}
                    </span>
                    <button
                        type="button"
                        disabled={safePage >= pageCount - 1}
                        onClick={() => setPage((p) => p + 1)}
                        data-testid="inbox-next"
                        className="rounded-lg border border-zinc-800 px-3 py-1.5 text-sm text-zinc-300 disabled:opacity-40"
                    >
                        next
                    </button>
                </div>
            )}
        </div>
    );
}
