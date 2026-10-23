import { CheckCircle2, Cpu, RefreshCw, Settings2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../App";
import { clearCloudKey, saveCloudKey } from "../lib/llm";
import { useLlm } from "../store/llm";

function StatusDot({ ok }: { ok: boolean }) {
    return ok ? (
        <CheckCircle2 className="h-4 w-4 text-green-400" />
    ) : (
        <XCircle className="h-4 w-4 text-zinc-400" />
    );
}

interface ChannelState {
    id: string;
    label: string;
    configured: boolean;
    detail: string;
    allowlist_count: number;
    setup_env: string;
    pairing_needed?: boolean;
    needs_auth?: boolean;
}

export default function Settings() {
    const {
        providers,
        models,
        gpus,
        selectedProvider,
        selectedModel,
        targetGpu,
        probing,
        selectProvider,
        selectModel,
        selectGpu,
        detect,
    } = useLlm();
    const [health, setHealth] = useState<string>("…");
    const [keyDraft, setKeyDraft] = useState<Record<string, string>>({});
    const [note, setNote] = useState<string | null>(null);
    const [channels, setChannels] = useState<ChannelState[] | null>(null);
    const [channelsError, setChannelsError] = useState<string | null>(null);

    useEffect(() => {
        void detect();
        api.get("/health")
            .then((r) => setHealth(`${r.data.status} · v${r.data.version}`))
            .catch(() => setHealth("unreachable"));
        api.get("/api/v1/channels")
            .then((r) => {
                setChannels(r.data.channels ?? []);
                setChannelsError(null);
            })
            .catch((e: unknown) =>
                setChannelsError(
                    e instanceof Error ? e.message : "unreachable",
                ),
            );
    }, [detect]);

    const saveKey = async (id: string) => {
        const value = keyDraft[id]?.trim();
        if (!value) return;
        try {
            await saveCloudKey(id, value);
            setKeyDraft((d) => ({ ...d, [id]: "" }));
            setNote(`Saved ${id} key`);
            await detect();
        } catch {
            setNote(`Failed to save ${id} key`);
        }
    };

    const removeKey = async (id: string) => {
        try {
            await clearCloudKey(id);
            setNote(`Removed ${id} key`);
            await detect();
        } catch {
            setNote(`Failed to remove ${id} key`);
        }
    };

    return (
        <div className="max-w-4xl space-y-6" data-testid="settings-page">
            <h1 className="flex items-center gap-2 text-2xl font-bold">
                <Settings2 className="h-5 w-5 text-amber-400" /> Settings
            </h1>

            <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
                <h2 className="text-sm font-semibold text-zinc-100">Backend</h2>
                <div className="mt-2 flex items-center gap-2 text-sm text-zinc-300">
                    <StatusDot ok={health.startsWith("ok")} />
                    <span data-testid="settings-health">{health}</span>
                    <button
                        type="button"
                        onClick={() => void detect()}
                        className="ml-auto rounded-lg border border-zinc-800 p-1.5 text-zinc-300 hover:text-white"
                    >
                        <RefreshCw className="h-4 w-4" />
                    </button>
                </div>
            </div>

            <div
                data-testid="channels-section"
                className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5"
            >
                <h2 className="text-sm font-semibold text-zinc-100">
                    Channels — auth & allowlists
                </h2>
                <p className="mt-1 text-sm text-zinc-400">
                    Secrets live in <span className="font-mono">.env</span> at
                    the repo root (never in the browser) — see Help → Channels
                    for exact names. Restart the backend after edits.
                </p>
                {channelsError && (
                    <div className="mt-3 text-sm text-red-300">
                        Channel status unreachable ({channelsError})
                    </div>
                )}
                <div className="mt-3 space-y-3">
                    {(channels ?? []).map((c) => (
                        <div
                            key={c.id}
                            data-testid={`channel-card-${c.id}`}
                            className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4"
                        >
                            <div className="flex items-center gap-2 text-sm">
                                <StatusDot ok={c.configured} />
                                <span className="font-medium text-zinc-100">
                                    {c.label}
                                </span>
                                <span className="ml-auto text-sm text-zinc-400">
                                    allowlist: {c.allowlist_count}
                                </span>
                            </div>
                            <div className="mt-1 text-sm text-zinc-300">
                                {c.detail}
                            </div>
                            {c.pairing_needed && (
                                <div className="mt-1 text-sm text-amber-300">
                                    Pairing needed — start wa-sidecar and scan
                                    the QR (GET :11208/qr on the backend host).
                                </div>
                            )}
                            {c.needs_auth && (
                                <div className="mt-1 text-sm text-amber-300">
                                    Auth needed — run{" "}
                                    <span className="font-mono">
                                        comms_ops(operation=&quot;auth&quot;,
                                        channel=&quot;teams&quot;)
                                    </span>{" "}
                                    in Claude/CLI, then enter the code.
                                </div>
                            )}
                            <div className="mt-1 font-mono text-sm text-zinc-500">
                                {c.setup_env}
                            </div>
                            <Link
                                to="/help"
                                className="mt-1 inline-block text-sm text-amber-300 underline"
                            >
                                Setup steps
                            </Link>
                        </div>
                    ))}
                    {channels !== null && channels.length === 0 && (
                        <div className="text-sm text-zinc-400">
                            No channel data — is the backend running?
                        </div>
                    )}
                </div>
            </div>

            <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
                <h2 className="text-sm font-semibold text-zinc-100">
                    Active model
                </h2>
                <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
                    <label className="text-zinc-400" htmlFor="provider-select">
                        Provider
                    </label>
                    <select
                        id="provider-select"
                        data-testid="llm-provider-select"
                        value={selectedProvider}
                        onChange={(e) => void selectProvider(e.target.value)}
                        className="rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1 text-zinc-100"
                    >
                        <option value="">
                            {probing ? "probing…" : "No local LLM detected"}
                        </option>
                        {providers.map((p) => (
                            <option
                                key={p.id}
                                value={p.id}
                                disabled={!p.configured}
                            >
                                {p.label}
                            </option>
                        ))}
                    </select>
                    <label className="text-zinc-400" htmlFor="model-select">
                        Model
                    </label>
                    <select
                        id="model-select"
                        data-testid="llm-model-select"
                        value={selectedModel}
                        onChange={(e) => selectModel(e.target.value)}
                        className="rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1 text-zinc-100"
                    >
                        {models.length === 0 && (
                            <option value="">no models</option>
                        )}
                        {models.map((m) => (
                            <option key={m} value={m}>
                                {m}
                            </option>
                        ))}
                    </select>
                </div>
                {gpus.length > 1 && (
                    <div className="mt-3 flex items-center gap-3 text-sm">
                        <Cpu className="h-4 w-4 text-amber-400" />
                        <label className="text-zinc-400" htmlFor="gpu-select">
                            GPU
                        </label>
                        <select
                            id="gpu-select"
                            data-testid="llm-gpu-select"
                            value={targetGpu}
                            onChange={(e) => selectGpu(Number(e.target.value))}
                            className="rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1 text-zinc-100"
                        >
                            {gpus.map((g) => (
                                <option key={g.index} value={g.index}>
                                    GPU {g.index} - {g.name} (
                                    {Math.round(g.total_mb / 1024)} GB)
                                </option>
                            ))}
                        </select>
                    </div>
                )}
            </div>

            <div className="space-y-3">
                <h2 className="text-sm font-semibold text-zinc-100">
                    Providers
                </h2>
                {note && <div className="text-sm text-amber-300">{note}</div>}
                {providers.map((p) => (
                    <div
                        key={p.id}
                        data-testid={`llm-provider-card-${p.id}`}
                        className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4"
                    >
                        <div className="flex items-center gap-2 text-sm">
                            <StatusDot ok={p.configured} />
                            <span className="font-medium text-zinc-100">
                                {p.label}
                            </span>
                            <span
                                className={`rounded px-1.5 py-0.5 text-sm ${
                                    p.kind === "local"
                                        ? "bg-green-500/10 text-green-300"
                                        : "bg-blue-500/10 text-blue-300"
                                }`}
                            >
                                {p.kind === "local"
                                    ? "Local / free"
                                    : "Cloud / paid"}
                            </span>
                            <span className="ml-auto font-mono text-sm text-zinc-400">
                                {p.base_url}
                            </span>
                        </div>
                        {p.needs_key && (
                            <div className="mt-3 flex flex-wrap items-center gap-2">
                                <input
                                    type="password"
                                    value={keyDraft[p.id] ?? ""}
                                    onChange={(e) =>
                                        setKeyDraft((d) => ({
                                            ...d,
                                            [p.id]: e.target.value,
                                        }))
                                    }
                                    placeholder={
                                        p.configured
                                            ? "key set — paste to replace"
                                            : `paste ${p.key_env}`
                                    }
                                    data-testid={`llm-key-${p.id}`}
                                    className="min-w-64 flex-1 rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-100"
                                />
                                <button
                                    type="button"
                                    onClick={() => void saveKey(p.id)}
                                    data-testid={`llm-test-${p.id}`}
                                    className="rounded-lg bg-amber-500 px-3 py-1.5 text-sm font-medium text-zinc-950 disabled:opacity-40"
                                    disabled={!keyDraft[p.id]?.trim()}
                                >
                                    Save & test
                                </button>
                                {p.configured && (
                                    <button
                                        type="button"
                                        onClick={() => void removeKey(p.id)}
                                        className="rounded-lg border border-zinc-800 px-3 py-1.5 text-sm text-zinc-300"
                                    >
                                        Clear
                                    </button>
                                )}
                            </div>
                        )}
                        {p.note && (
                            <div className="mt-2 text-sm text-zinc-400">
                                {p.note}
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}
