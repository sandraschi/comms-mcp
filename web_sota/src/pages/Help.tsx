import { HelpCircle } from "lucide-react";

const STEPS = [
    "Create a bot with @BotFather and copy the token.",
    "Set COMMS_TELEGRAM_BOT_TOKEN and COMMS_TELEGRAM_CHAT_IDS in .env (repo root).",
    "Start the backend: uv run python -m comms_mcp (MCP_PORT=11205 for the daemon).",
    'Message the bot once, then run comms_ops(operation="read_recent") — the chat id appears there; add it to the allowlist.',
    'comms_ops(operation="status") shows the bot + allowlist + stats.',
];

export default function Help() {
    return (
        <div data-testid="help-page" className="max-w-2xl">
            <h1 className="text-2xl font-bold">Help</h1>
            <div className="mt-4 rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
                <h2 className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
                    <HelpCircle className="h-4 w-4 text-amber-400" /> Telegram
                    setup
                </h2>
                <ol className="mt-3 space-y-2 text-sm text-zinc-300">
                    {STEPS.map((s, i) => (
                        <li key={i} className="flex gap-3">
                            <span className="text-zinc-400">{i + 1}.</span>
                            <span>{s}</span>
                        </li>
                    ))}
                </ol>
            </div>

            <div
                data-testid="help-mcp-surface"
                className="mt-4 rounded-xl border border-zinc-800 bg-zinc-900/20 p-4 text-sm text-zinc-300"
            >
                <div className="font-medium text-zinc-100">MCP surface</div>
                <pre className="mt-2 overflow-x-auto rounded-lg bg-zinc-950 p-3 text-xs text-zinc-300">
                    {`comms_ops(operation="send", channel="telegram", chat_id="…", text="…")
comms_ops(operation="read_recent", channel="telegram")
comms_ops(operation="list_threads", channel="telegram")
comms_ops(operation="status", channel="telegram")`}
                </pre>
            </div>

            <div
                data-testid="help-retention"
                className="mt-4 rounded-xl border border-zinc-800 bg-zinc-900/20 p-4 text-sm text-zinc-400"
            >
                Inbound is sanitized (prompt-injection neutralized) and retained
                7 days by default (COMMS_RETENTION_DAYS). Send is
                allowlist-gated server-side. Channels: Telegram, WhatsApp
                (baileys sidecar), Slack (Socket Mode), Teams (Graph device
                flow) — full steps in docs/ONBOARDING.md.
            </div>
        </div>
    );
}
