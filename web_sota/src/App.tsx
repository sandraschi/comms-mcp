import axios from "axios";
import { HelpCircle, Inbox, LayoutDashboard, Send, Shield } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import Allowlist from "./pages/Allowlist";
import Dashboard from "./pages/Dashboard";
import Help from "./pages/Help";
import Outbox from "./pages/Outbox";

const api = axios.create({ baseURL: "/api", timeout: 10000 });

export interface StatusData {
    configured: boolean;
    bot: string | null;
    allowlist: string[];
    stats: { outbox: Record<string, number>; inbound_total: number };
    retention_days: number;
}

export const useStatus = () => {
    const [status, setStatus] = useState<StatusData | null>(null);
    const refresh = async () => {
        try {
            const r = await api.get("/v1/status");
            setStatus(r.data);
        } catch {
            setStatus(null);
        }
    };
    useEffect(() => {
        let timer: ReturnType<typeof setTimeout>;
        let fails = 0;
        // Exponential backoff while the backend is down (1s..16s), steady
        // 15s poll once it answers.
        const tick = async () => {
            try {
                const r = await api.get("/v1/status");
                setStatus(r.data);
                fails = 0;
                timer = setTimeout(tick, 15000);
            } catch {
                setStatus(null);
                fails += 1;
                timer = setTimeout(
                    tick,
                    Math.min(1000 * 2 ** (fails - 1), 16000),
                );
            }
        };
        tick();
        return () => clearTimeout(timer);
    }, []);
    return { status, refresh };
};

const NAV = [
    { to: "/", label: "Dashboard", icon: LayoutDashboard },
    { to: "/outbox", label: "Outbox", icon: Send },
    { to: "/allowlist", label: "Allowlist", icon: Shield },
    { to: "/help", label: "Help", icon: HelpCircle },
];

export default function App() {
    return (
        <div
            className="flex min-h-screen bg-zinc-950 text-zinc-100"
            data-testid="comms-console"
        >
            <aside className="w-52 shrink-0 border-r border-zinc-800 bg-zinc-900/40 p-4">
                <div className="mb-6 flex items-center gap-2">
                    <Inbox className="h-5 w-5 text-amber-400" />
                    <div>
                        <div className="text-sm font-semibold">comms-mcp</div>
                        <div className="text-sm text-zinc-300">
                            v0.4 · 4 channels
                        </div>
                    </div>
                </div>
                <nav className="space-y-1">
                    {NAV.map((n) => (
                        <NavLink
                            key={n.to}
                            to={n.to}
                            className={({ isActive }) =>
                                `flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors ${
                                    isActive
                                        ? "bg-amber-500/10 text-amber-300"
                                        : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
                                }`
                            }
                        >
                            <n.icon className="h-4 w-4" />
                            {n.label}
                        </NavLink>
                    ))}
                </nav>
            </aside>
            <main className="flex-1 p-8">
                <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/outbox" element={<Outbox />} />
                    <Route path="/allowlist" element={<Allowlist />} />
                    <Route path="/help" element={<Help />} />
                </Routes>
            </main>
        </div>
    );
}

export { api };
