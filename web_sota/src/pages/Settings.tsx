import { CheckCircle2, Cpu, RefreshCw, Settings2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../App";
import { clearCloudKey, saveCloudKey } from "../lib/llm";
import { useLlm } from "../store/llm";

function StatusDot({ ok }: { ok: boolean }) {
    return ok ? (
        <CheckCircle2 className="h-4 w-4 text-green-400" />
    ) : (
        <XCircle className="h-4 w-4 text-zinc-500" />
    );
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

    useEffect(() => {
        void detect();
        api.get("/health")
            .then((r) => setHealth(`${r.data.status} · v${r.data.version}`))
            .catch(() => setHealth("unreachable"));
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
