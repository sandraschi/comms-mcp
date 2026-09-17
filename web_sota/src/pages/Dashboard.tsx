import { useState } from 'react';
import { Send, RefreshCw, Activity } from 'lucide-react';
import { api, useStatus } from '../App';

export default function Dashboard() {
    const { status, refresh } = useStatus();
    const [chatId, setChatId] = useState('');
    const [text, setText] = useState('');
    const [sending, setSending] = useState(false);
    const [result, setResult] = useState<string | null>(null);

    const testSend = async () => {
        setSending(true);
        setResult(null);
        try {
            const r = await api.post('/v1/send', { chat_id: chatId, text });
            setResult(`sent (outbox #${r.data.outbox_id})`);
        } catch (e: any) {
            setResult(`error: ${e.response?.data?.error || e.message}`);
        }
        setSending(false);
        refresh();
    };

    const outboxTotal = Object.values(status?.stats?.outbox || {}).reduce((a, b) => a + b, 0);

    return (
        <div className="space-y-6" data-testid="dashboard">
            <div className="flex items-center justify-between">
                <h1 className="text-2xl font-bold">Dashboard</h1>
                <button onClick={refresh} className="rounded-lg border border-zinc-800 p-2 text-zinc-400 hover:text-white">
                    <RefreshCw className="h-4 w-4" />
                </button>
            </div>

            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4" data-testid="kpi-bot">
                    <div className="text-xs text-zinc-500">Bot</div>
                    <div className="mt-1 flex items-center gap-2 text-lg font-semibold">
                        <span className={`h-2 w-2 rounded-full ${status?.configured ? 'bg-green-500' : 'bg-red-500'}`} />
                        {status?.configured ? `@${status.bot}` : 'not configured'}
                    </div>
                </div>
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4" data-testid="kpi-allowlist">
                    <div className="text-xs text-zinc-500">Allowlist</div>
                    <div className="mt-1 text-lg font-semibold">{status?.allowlist.length ?? '…'} chats</div>
                </div>
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4" data-testid="kpi-outbox">
                    <div className="text-xs text-zinc-500">Outbox</div>
                    <div className="mt-1 text-lg font-semibold">{outboxTotal}</div>
                </div>
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4" data-testid="kpi-retention">
                    <div className="text-xs text-zinc-500">Retention</div>
                    <div className="mt-1 text-lg font-semibold">{status?.retention_days ?? '…'} days</div>
                </div>
            </div>

            <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
                <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-zinc-200">
                    <Send className="h-4 w-4 text-amber-400" /> Test send
                </h2>
                <div className="space-y-3">
                    <input
                        value={chatId}
                        onChange={(e) => setChatId(e.target.value)}
                        placeholder="chat id (must be allowlisted)"
                        data-testid="test-chat-id"
                        className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm outline-none focus:border-amber-500/50"
                    />
                    <textarea
                        value={text}
                        onChange={(e) => setText(e.target.value)}
                        rows={2}
                        placeholder="message text"
                        data-testid="test-text"
                        className="w-full resize-none rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm outline-none focus:border-amber-500/50"
                    />
                    <div className="flex items-center gap-3">
                        <button
                            onClick={testSend}
                            disabled={sending || !chatId || !text.trim()}
                            data-testid="test-send"
                            className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-zinc-950 disabled:opacity-40"
                        >
                            {sending ? 'Sending…' : 'Send'}
                        </button>
                        {result && <span className="text-xs text-zinc-400">{result}</span>}
                    </div>
                </div>
            </div>

            <div className="flex items-center gap-2 text-xs text-zinc-600">
                <Activity className="h-3.5 w-3.5" />
                backend :10904 · console :10903 · inbound sanitized · 7-day TTL
            </div>
        </div>
    );
}

