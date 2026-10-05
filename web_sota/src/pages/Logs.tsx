import { ScrollText } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../App";

interface LogEntry {
    time: string;
    level: string;
    source: string;
    message: string;
}

const LEVELS = ["", "DEBUG", "INFO", "WARNING", "ERROR"];

export default function Logs() {
    const [entries, setEntries] = useState<LogEntry[]>([]);
    const [level, setLevel] = useState("");
    const [search, setSearch] = useState("");
    const [error, setError] = useState<string | null>(null);

    const load = async () => {
        try {
            const r = await api.get("/logs", {
                params: { level, search, limit: 200 },
            });
            setEntries(r.data.entries);
            setError(null);
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : "load failed");
        }
    };

    useEffect(() => {
        void load();
        const t = setInterval(() => void load(), 5000);
        return () => clearInterval(t);
    }, [level, search]);

    return (
        <div className="max-w-5xl space-y-4" data-testid="logs-page">
            <h1 className="flex items-center gap-2 text-2xl font-bold">
                <ScrollText className="h-5 w-5 text-amber-400" /> Logs
            </h1>
            <div className="flex flex-wrap items-center gap-2">
                <select
                    value={level}
                    onChange={(e) => setLevel(e.target.value)}
                    data-testid="logs-level"
                    className="rounded-lg border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-sm text-zinc-100"
                >
                    {LEVELS.map((l) => (
                        <option key={l} value={l}>
                            {l || "all levels"}
                        </option>
                    ))}
                </select>
                <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="search message…"
                    data-testid="logs-search"
                    className="min-w-52 flex-1 rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-100 outline-none focus:border-amber-500/50"
                />
                <span
                    data-testid="logs-count"
                    className="text-sm text-zinc-400"
                >
                    {entries.length} entries
                </span>
            </div>
            {error && (
                <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
                    {error}
                </div>
            )}
            <div
                className="space-y-1 font-mono text-sm"
                data-testid="logs-entries"
            >
                {entries.length === 0 && (
                    <div className="text-zinc-400">No log records yet.</div>
                )}
                {entries.map((e, i) => (
                    <div
                        key={i}
                        className="flex gap-3 rounded border border-zinc-900 bg-zinc-900/30 px-3 py-1.5"
                    >
                        <span className="text-zinc-500">
                            {new Date(e.time).toLocaleTimeString()}
                        </span>
                        <span
                            className={`w-16 ${
                                e.level === "ERROR"
                                    ? "text-red-300"
                                    : e.level === "WARNING"
                                      ? "text-amber-300"
                                      : "text-zinc-400"
                            }`}
                        >
                            {e.level}
                        </span>
                        <span className="text-zinc-200">{e.message}</span>
                    </div>
                ))}
            </div>
        </div>
    );
}
