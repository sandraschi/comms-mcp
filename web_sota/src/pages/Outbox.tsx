import { useEffect, useState } from 'react';
import { api } from '../App';

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

const STATUS_FILTERS = ['', 'pending', 'sent', 'failed'];

export default function Outbox() {
    const [items, setItems] = useState<OutboxItem[]>([]);
    const [filter, setFilter] = useState('');
    const [loading, setLoading] = useState(false);

    const load = async (status: string) => {
        setLoading(true);
        try {
            const r = await api.get('/v1/outbox', { params: { status, limit: 50 } });
            setItems(r.data.items);
        } catch {
            setItems([]);
        }
        setLoading(false);
    };

    useEffect(() => {
        load(filter);
    }, [filter]);

    const badge = (s: string) =>
        s === 'sent'
            ? 'bg-green-500/10 text-green-400'
            : s === 'failed'
              ? 'bg-red-500/10 text-red-400'
              : 'bg-amber-500/10 text-amber-400';

    return (
        <div data-testid="outbox-page">
            <h1 className="text-2xl font-bold">Outbox</h1>
            <div className="mt-4 flex gap-2">
                {STATUS_FILTERS.map((s) => (
                    <button
                        key={s || 'all'}
                        onClick={() => setFilter(s)}
                        className={`rounded-lg px-3 py-1.5 text-sm border ${
                            filter === s
                                ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
                                : 'border-zinc-800 text-zinc-400'
                        }`}
                    >
                        {s || 'all'}
                    </button>
                ))}
            </div>
            <div className="mt-4 space-y-2">
                {loading && <div className="text-sm text-zinc-500">Loading…</div>}
                {!loading && items.length === 0 && (
                    <div className="rounded-xl border border-dashed border-zinc-800 p-8 text-center text-sm text-zinc-600">
                        No outbox items
                    </div>
                )}
                {items.map((it) => (
                    <div key={it.id} className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
                        <div className="flex items-center gap-3 text-xs text-zinc-500">
                            <span className={`rounded px-2 py-0.5 text-[10px] font-medium ${badge(it.status)}`}>
                                {it.status}
                            </span>
                            <span>#{it.id}</span>
                            <span className="text-amber-400/80">{it.chat_id}</span>
                            <span>{new Date(it.created_at).toLocaleString()}</span>
                            {it.error && <span className="text-red-400">({it.error})</span>}
                        </div>
                        <div className="mt-1.5 text-sm text-zinc-300">{it.text}</div>
                    </div>
                ))}
            </div>
        </div>
    );
}

