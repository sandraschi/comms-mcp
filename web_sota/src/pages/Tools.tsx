import { Wrench } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../App";

interface Capabilities {
    server: string;
    version: string;
    channels: string[];
    mcp_tools: string[];
    rest: string[];
    webhook_secret_configured: boolean;
}

export default function Tools() {
    const [caps, setCaps] = useState<Capabilities | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        api.get("/capabilities")
            .then((r) => setCaps(r.data))
            .catch(() => setError("could not load capabilities"));
    }, []);

    return (
        <div className="max-w-4xl space-y-4" data-testid="tools-page">
            <h1 className="flex items-center gap-2 text-2xl font-bold">
                <Wrench className="h-5 w-5 text-amber-400" /> Tools
            </h1>
            {error && (
                <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
                    {error}
                </div>
            )}
            {caps && (
                <>
                    <div className="flex flex-wrap gap-2 text-sm">
                        <span className="rounded-lg border border-zinc-800 px-2 py-1 text-zinc-300">
                            {caps.server} v{caps.version}
                        </span>
                        {caps.channels.map((c) => (
                            <span
                                key={c}
                                className="rounded-lg bg-amber-500/10 px-2 py-1 text-amber-300"
                            >
                                {c}
                            </span>
                        ))}
                    </div>
                    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
                        <h2 className="text-sm font-semibold text-zinc-100">
                            MCP tools ({caps.mcp_tools.length})
                        </h2>
                        <div
                            className="mt-2 flex flex-wrap gap-2"
                            data-testid="tools-mcp"
                        >
                            {caps.mcp_tools.map((t) => (
                                <span
                                    key={t}
                                    className="rounded-lg border border-zinc-700 bg-zinc-800/60 px-3 py-1.5 font-mono text-sm text-zinc-100"
                                >
                                    {t}
                                </span>
                            ))}
                        </div>
                    </div>
                    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
                        <h2 className="text-sm font-semibold text-zinc-100">
                            REST ({caps.rest.length})
                        </h2>
                        <ul
                            data-testid="tools-rest"
                            className="mt-2 space-y-1 font-mono text-sm text-zinc-300"
                        >
                            {caps.rest.map((r) => (
                                <li key={r}>{r}</li>
                            ))}
                        </ul>
                    </div>
                </>
            )}
        </div>
    );
}
