import axios from "axios";
import { Activity, Inbox, RefreshCw, Send } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, useStatus } from "../App";

function sendError(e: unknown): string {
    if (axios.isAxiosError(e)) {
        const data = e.response?.data as { error?: string } | undefined;
        return data?.error ?? e.message;
    }
    return e instanceof Error ? e.message : String(e);
}

export default function Dashboard() {
    const { status, refresh } = useStatus();
    const [chatId, setChatId] = useState("");
    const [text, setText] = useState("");
    const [sending, setSending] = useState(false);
    const [result, setResult] = useState<string | null>(null);
    const [loadError, setLoadError] = useState<string | null>(null);

    const testSend = async () => {
        setSending(true);
        setResult(null);
        try {
            const r = await api.post("/v1/send", { chat_id: chatId, text });
            setResult(`sent (outbox #${r.data.outbox_id})`);
            setLoadError(null);
        } catch (e: unknown) {
            setResult(`error: ${sendError(e)}`);
        }
        setSending(false);
        try {
            await refresh();
        } catch (e: unknown) {
            setLoadError(sendError(e));
        }
    };

    const reload = async () => {
        try {
            await refresh();
            setLoadError(null);
        } catch (e: unknown) {
            setLoadError(sendError(e));
        }
    };

    const outboxTotal = Object.values(status?.stats?.outbox || {}).reduce(
        (a, b) => a + b,
        0,
    );
    const onboarded = Boolean(
        status?.configured && (status?.allowlist.length ?? 0) > 0,
    );
    // MOCK-until-onboarded (ONBOARDING_STANDARD § Mock-until-onboarded):
    // show clearly-badged sample data while unconfigured so the console is not
    // a wall of zeros; the samples disappear the moment onboarding succeeds.
    const mock = !onboarded && status !== null;
    const mockTag = mock ? (
        <span
            data-testid="mock-badge"
            className="ml-2 rounded bg-amber-500/20 px-1.5 py-0.5 text-sm font-medium text-amber-300"
        >
            MOCK
        </span>
    ) : null;

    return (
        <div className="space-y-6" data-testid="dashboard">
            <div data-testid="hero">
                <h1 className="flex items-center gap-2 text-2xl font-bold">
                    <Inbox className="h-6 w-6 text-amber-400" />
                    Fleet comms console
                </h1>
                <p className="mt-1 max-w-2xl text-sm text-zinc-300">
                    Send and read Telegram, WhatsApp, Slack, and Teams from one
                    place. Sends are allowlist-gated server-side; inbound is
                    sanitized and retained {status?.retention_days ?? 7} days.
                    Start below with a test send, or open Help for per-channel
                    setup.
                </p>
            </div>

            {!onboarded && (
                <Link
                    to="/help"
                    data-testid="onboarding-cue"
                    className="block rounded-xl border border-red-500/50 bg-red-500/10 p-4 text-sm text-red-200 hover:bg-red-500/20"
                >
                    <span className="font-semibold">Not onboarded:</span> no bot
                    configured or allowlist empty — follow the 2-minute setup in
                    Help to send your first message.
                </Link>
            )}

            <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">Status</h2>
                <button
                    type="button"
                    onClick={reload}
                    data-testid="refresh-status"
                    className="rounded-lg border border-zinc-800 p-2 text-zinc-300 hover:text-white"
                >
                    <RefreshCw className="h-4 w-4" />
                </button>
            </div>
            {loadError && (
                <div className="rounded-xl border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
                    Backend unreachable ({loadError}){" "}
                    <button
                        type="button"
                        onClick={reload}
                        className="underline"
                    >
                        retry
                    </button>
                </div>
            )}

            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <div
                    className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4"
                    data-testid="kpi-bot"
                >
                    <div className="text-sm text-zinc-300">Bot</div>
                    <div className="mt-1 flex items-center gap-2 text-lg font-semibold">
                        <span
                            data-testid="backend-dot"
                            className={`h-2 w-2 rounded-full ${status?.configured ? "bg-green-500" : "bg-red-500"}`}
                        />
                        {mock
                            ? "Joe Mocky (sample)"
                            : status?.configured
                              ? `@${status.bot}`
                              : "not configured"}
                        {mockTag}
                    </div>
                </div>
                <div
                    className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4"
                    data-testid="kpi-allowlist"
                >
                    <div className="text-sm text-zinc-300">Allowlist</div>
                    <div className="mt-1 text-lg font-semibold">
                        {mock ? 3 : (status?.allowlist.length ?? "…")} chats
                        {mockTag}
                    </div>
                </div>
                <div
                    className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4"
                    data-testid="kpi-outbox"
                >
                    <div className="text-sm text-zinc-300">Outbox</div>
                    <div className="mt-1 text-lg font-semibold">
                        {mock ? 12 : outboxTotal}
                        {mockTag}
                    </div>
                </div>
                <div
                    className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4"
                    data-testid="kpi-retention"
                >
                    <div className="text-sm text-zinc-300">Retention</div>
                    <div className="mt-1 text-lg font-semibold">
                        {status?.retention_days ?? "…"} days
                    </div>
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
                        className="w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-amber-500/50"
                    />
                    <textarea
                        value={text}
                        onChange={(e) => setText(e.target.value)}
                        rows={2}
                        placeholder="message text"
                        data-testid="test-text"
                        className="w-full resize-none rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-amber-500/50"
                    />
                    <div className="flex items-center gap-3">
                        <button
                            type="button"
                            onClick={testSend}
                            disabled={sending || !chatId || !text.trim()}
                            data-testid="test-send"
                            className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-zinc-950 disabled:opacity-40"
                        >
                            {sending ? "Sending…" : "Send"}
                        </button>
                        {result && (
                            <span
                                data-testid="test-result"
                                className="text-sm text-zinc-300"
                            >
                                {result}
                            </span>
                        )}
                    </div>
                </div>
            </div>

            <div className="flex items-center gap-2 text-sm text-zinc-400">
                <Activity className="h-3.5 w-3.5" />
                serving {window.location.host} · inbound sanitized ·{" "}
                {status?.retention_days ?? 7}-day TTL
            </div>
        </div>
    );
}
