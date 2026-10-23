import { HelpCircle } from "lucide-react";
import { useState } from "react";

type TabId = "overview" | "channels" | "api" | "troubleshoot" | "faq";

const TABS: Array<{ id: TabId; name: string; blurb: string }> = [
    { id: "overview", name: "Overview", blurb: "What this console is" },
    { id: "channels", name: "Channels", blurb: "Per-channel setup" },
    { id: "api", name: "API & ports", blurb: "Ports, env, endpoints" },
    {
        id: "troubleshoot",
        name: "Fixes",
        blurb: "Symptom → cause → fix",
    },
    { id: "faq", name: "FAQ", blurb: "Asked, not imagined" },
];

const CHANNELS = [
    {
        id: "telegram",
        title: "Telegram",
        steps: [
            "Create a bot with @BotFather and copy the token.",
            "Set COMMS_TELEGRAM_BOT_TOKEN and COMMS_TELEGRAM_CHAT_IDS (comma-separated chat ids) in .env, repo root.",
            "Start the backend: uv run python -m comms_mcp (daemon on :11205).",
            'Message the bot once, then run comms_ops(operation="read_recent") — the chat id appears there; add it to the allowlist.',
            'comms_ops(operation="status", channel="telegram") shows the bot + allowlist + stats.',
            'Replies: send with thread_ts = message id. HTML formatting via parse_mode="HTML".',
        ],
    },
    {
        id: "whatsapp",
        title: "WhatsApp (baileys sidecar)",
        steps: [
            "Start the sidecar: node wa-sidecar (listens on :11208).",
            "Open Settings → Channels → WhatsApp card: the pairing QR/code shows while disconnected.",
            "Scan the QR with the phone (Linked devices), or use the pairing code.",
            "Set COMMS_WHATSAPP_ALLOW_NUMBERS (comma-separated E.164, e.g. +436991234567).",
            "History = local inbound store — the sidecar exposes no chat list API.",
        ],
    },
    {
        id: "slack",
        title: "Slack (Socket Mode)",
        steps: [
            "Create a Slack app with Socket Mode + scopes channels:history, channels:read, chat:write, reactions:write, search:read.",
            "Set COMMS_SLACK_APP_TOKEN (xapp-*) + COMMS_SLACK_BOT_TOKEN (xoxb-*) + COMMS_SLACK_CHANNEL_IDS.",
            "Invite the bot to each allowlisted channel.",
            "History/search/react/edit/delete need the channel id as chat_id; thread replies via thread_ts.",
        ],
    },
    {
        id: "teams",
        title: "Teams (Graph device flow)",
        steps: [
            "Reuse email-mcp's Azure app registration, or create one (Entra → App registrations).",
            "Set COMMS_GRAPH_CLIENT_ID + COMMS_TEAMS_RECIPIENTS (name=email or name=19:chatId).",
            'Run comms_ops(operation="auth", channel="teams") — enter the code at microsoft.com/devicelogin, then call again to confirm.',
            "Attendance/recordings/transcripts need admin consent for OnlineMeetingArtifact.Read.All.",
        ],
    },
];

const FIXES = [
    {
        symptom: "Dashboard shows MOCK badges (Joe Mocky)",
        cause: "No bot configured or allowlist empty — mock-until-onboarded samples.",
        fix: "Settings → Channels: configure one channel + allowlist, restart backend. Badges clear automatically.",
    },
    {
        symptom: "Backend unreachable (red panel)",
        cause: "Backend down or wrong port — frontend polls :11205.",
        fix: "Start backend: uv run python -m comms_mcp. Retry button re-polls.",
    },
    {
        symptom: "send → 403 chat not in allowlist",
        cause: "chat_id not in the channel allowlist (server-side gate).",
        fix: "Add the id to the channel's allowlist env (see Channels tab), restart backend.",
    },
    {
        symptom: "WhatsApp status never connects",
        cause: "Sidecar not running or session expired.",
        fix: "node wa-sidecar, rescan QR from Settings → Channels → WhatsApp.",
    },
    {
        symptom: "Teams auth: 403 Authorization_RequestDenied",
        cause: "Missing admin consent for OnlineMeetingArtifact.Read.All.",
        fix: "Entra admin grants consent on the app registration; retry auth poll.",
    },
    {
        symptom: "Slack events never arrive",
        cause: "Bot not invited to the channel, or Socket Mode token wrong.",
        fix: "Invite bot to channel; verify COMMS_SLACK_APP_TOKEN starts with xapp-.",
    },
];

const FAQS = [
    {
        q: "Where is my data?",
        a: "SQLite at data/comms.db (outbox) + inbound bodies with 7-day TTL (COMMS_RETENTION_DAYS). Token cache for Teams at data/teams_oauth.json. Nothing leaves the machine except the channel APIs themselves.",
    },
    {
        q: "Where do I put tokens and allowlists?",
        a: "Settings → Channels shows live per-channel status; values live in .env at the repo root (see Channels tab for exact names). Restart the backend after edits — config is read at startup.",
    },
    {
        q: "How do clients connect?",
        a: "MCP over stdio (uv run python -m comms_mcp) or streamable HTTP at :11205/mcp. Claude Desktop: point the server entry at the repo. Single tool: comms_ops.",
    },
    {
        q: "Which service restarts after a code change?",
        a: "Backend only (uv run python -m comms_mcp). The Vite dev server hot-reloads the frontend. wa-sidecar only when its own code changes.",
    },
    {
        q: "Where are the logs?",
        a: "Logs page (GET /api/logs ring buffer) plus stderr of the backend process.",
    },
    {
        q: "Does chat use my fleet messages as training data?",
        a: "No. Chat calls your local LLM (Ollama/LM Studio) or your own cloud key. Skill content + your prompt are the only context.",
    },
];

export default function Help() {
    const [tab, setTab] = useState<TabId>("overview");
    const [query, setQuery] = useState("");
    const q = query.trim().toLowerCase();
    const fixes = FIXES.filter(
        (f) =>
            !q ||
            f.symptom.toLowerCase().includes(q) ||
            f.cause.toLowerCase().includes(q) ||
            f.fix.toLowerCase().includes(q),
    );
    const faqs = FAQS.filter(
        (f) =>
            !q ||
            f.q.toLowerCase().includes(q) ||
            f.a.toLowerCase().includes(q),
    );

    return (
        <div data-testid="help-page" className="max-w-3xl">
            <h1 className="flex items-center gap-2 text-2xl font-bold">
                <HelpCircle className="h-5 w-5 text-amber-400" /> Help
            </h1>

            <div
                data-testid="help-tabs"
                className="mt-4 flex gap-1 border-b border-zinc-800"
            >
                {TABS.map((t) => (
                    <button
                        key={t.id}
                        type="button"
                        data-testid={`help-tab-${t.id}`}
                        onClick={() => setTab(t.id)}
                        title={t.blurb}
                        className={`px-3 py-2 text-sm ${
                            tab === t.id
                                ? "border-b-2 border-amber-400 font-medium text-amber-200"
                                : "text-zinc-400 hover:text-zinc-200"
                        }`}
                    >
                        {t.name}
                    </button>
                ))}
            </div>

            {(tab === "troubleshoot" || tab === "faq") && (
                <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="filter fixes / faq…"
                    data-testid="help-search"
                    className="mt-4 w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-amber-500/50"
                />
            )}

            {tab === "overview" && (
                <div className="mt-4 space-y-4 text-sm text-zinc-300">
                    <p>
                        comms-mcp is one text gateway for four channels —
                        Telegram, WhatsApp, Slack, Teams. One portmanteau tool
                        (comms_ops), allowlist-gated sends, sanitized inbound
                        kept 7 days. This console sends, reads, and onboards it.
                    </p>
                    <ul className="list-disc space-y-1 pl-5">
                        <li>Dashboard — KPIs, test send, onboarding cue.</li>
                        <li>Inbox / Outbox — inbound store, send queue.</li>
                        <li>
                            Chat — skill-first LLM console (local or cloud).
                        </li>
                        <li>
                            Tools — live capability surface (never hardcoded).
                        </li>
                        <li>Skills — server SKILL.md sources for agents.</li>
                        <li>Allowlist — current gates (read-only).</li>
                        <li>
                            Settings — backend + LLM + per-channel setup state.
                        </li>
                        <li>Logs — backend ring buffer.</li>
                    </ul>
                    <div
                        data-testid="help-retention"
                        className="rounded-xl border border-zinc-800 bg-zinc-900/20 p-4 text-zinc-400"
                    >
                        Inbound is sanitized (prompt-injection neutralized) and
                        retained 7 days by default (COMMS_RETENTION_DAYS). Sends
                        are allowlist-gated server-side.
                    </div>
                </div>
            )}

            {tab === "channels" && (
                <div className="mt-4 space-y-4">
                    {CHANNELS.map((c) => (
                        <div
                            key={c.id}
                            data-testid={`help-channel-${c.id}`}
                            className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5"
                        >
                            <h2 className="text-sm font-semibold text-zinc-100">
                                {c.title} setup
                            </h2>
                            <ol className="mt-3 space-y-2 text-sm text-zinc-300">
                                {c.steps.map((s, i) => (
                                    <li key={i} className="flex gap-3">
                                        <span className="text-zinc-400">
                                            {i + 1}.
                                        </span>
                                        <span>{s}</span>
                                    </li>
                                ))}
                            </ol>
                        </div>
                    ))}
                    <p className="text-sm text-zinc-400">
                        Full narrative: docs/ONBOARDING.md in the repo.
                    </p>
                </div>
            )}

            {tab === "api" && (
                <div className="mt-4 space-y-4 text-sm text-zinc-300">
                    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
                        <div className="font-medium text-zinc-100">Ports</div>
                        <table className="mt-2 w-full text-sm">
                            <tbody>
                                <tr className="border-t border-zinc-800">
                                    <td className="py-1 font-mono">11204</td>
                                    <td className="py-1">
                                        Frontend (Vite dev)
                                    </td>
                                </tr>
                                <tr className="border-t border-zinc-800">
                                    <td className="py-1 font-mono">11205</td>
                                    <td className="py-1">
                                        Backend (REST + FastMCP /mcp)
                                    </td>
                                </tr>
                                <tr className="border-t border-zinc-800">
                                    <td className="py-1 font-mono">11208</td>
                                    <td className="py-1">
                                        WhatsApp sidecar (Node)
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
                        <div className="font-medium text-zinc-100">
                            Env vars (repo-root .env, restart after edits)
                        </div>
                        <ul className="mt-2 space-y-1 font-mono text-sm">
                            <li>
                                COMMS_TELEGRAM_BOT_TOKEN /
                                COMMS_TELEGRAM_CHAT_IDS
                            </li>
                            <li>
                                COMMS_WHATSAPP_ALLOW_NUMBERS /
                                COMMS_WHATSAPP_SIDECAR_URL
                            </li>
                            <li>
                                COMMS_SLACK_APP_TOKEN / COMMS_SLACK_BOT_TOKEN /
                                COMMS_SLACK_CHANNEL_IDS
                            </li>
                            <li>
                                COMMS_GRAPH_CLIENT_ID / COMMS_TEAMS_RECIPIENTS
                            </li>
                            <li>COMMS_RETENTION_DAYS / COMMS_INBOUND_SECRET</li>
                        </ul>
                    </div>
                    <div
                        data-testid="help-mcp-surface"
                        className="rounded-xl border border-zinc-800 bg-zinc-900/20 p-4"
                    >
                        <div className="font-medium text-zinc-100">
                            MCP surface
                        </div>
                        <pre className="mt-2 overflow-x-auto rounded-lg bg-zinc-950 p-3 text-sm text-zinc-300">
                            {`comms_ops(operation="send", channel="telegram", chat_id="…", text="…")
comms_ops(operation="read_recent", channel="slack", chat_id="C…")
comms_ops(operation="history", channel="teams", chat_id="steve")
comms_ops(operation="search", channel="slack", query="…")
comms_ops(operation="react", channel="slack", chat_id="C…", thread_ts="…", emoji="…")
comms_ops(operation="edit" | "delete", channel="telegram", chat_id="…", thread_ts="…")
comms_ops(operation="status", channel="telegram")
comms_ops(operation="auth", channel="teams")`}
                        </pre>
                    </div>
                </div>
            )}

            {tab === "troubleshoot" && (
                <div data-testid="help-fixes" className="mt-4 space-y-3">
                    {fixes.map((f) => (
                        <div
                            key={f.symptom}
                            className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 text-sm"
                        >
                            <div className="font-medium text-zinc-100">
                                {f.symptom}
                            </div>
                            <div className="mt-1 text-zinc-400">
                                Cause: {f.cause}
                            </div>
                            <div className="mt-1 text-zinc-300">
                                Fix: {f.fix}
                            </div>
                        </div>
                    ))}
                    {fixes.length === 0 && (
                        <div className="text-sm text-zinc-400">
                            No fixes match “{query}”.
                        </div>
                    )}
                </div>
            )}

            {tab === "faq" && (
                <div data-testid="help-faq" className="mt-4 space-y-3">
                    {faqs.map((f) => (
                        <details
                            key={f.q}
                            data-testid="faq-item"
                            className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 text-sm"
                        >
                            <summary className="cursor-pointer font-medium text-zinc-100">
                                {f.q}
                            </summary>
                            <div className="mt-2 text-zinc-300">{f.a}</div>
                        </details>
                    ))}
                    {faqs.length === 0 && (
                        <div className="text-sm text-zinc-400">
                            No answers match “{query}”.
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
