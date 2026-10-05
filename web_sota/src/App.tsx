import axios from "axios";
import {
    BookOpen,
    Bot,
    HelpCircle,
    Inbox as InboxIcon,
    LayoutDashboard,
    ScrollText,
    Send,
    Settings2,
    Shield,
    Wrench,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import Allowlist from "./pages/Allowlist";
import Chat from "./pages/Chat";
import Dashboard from "./pages/Dashboard";
import Help from "./pages/Help";
import Inbox from "./pages/Inbox";
import Logs from "./pages/Logs";
import Outbox from "./pages/Outbox";
import Settings from "./pages/Settings";
import Skills from "./pages/Skills";
import Tools from "./pages/Tools";

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
    { to: "/inbox", label: "Inbox", icon: InboxIcon },
    { to: "/outbox", label: "Outbox", icon: Send },
    { to: "/chat", label: "Chat", icon: Bot },
    { to: "/tools", label: "Tools", icon: Wrench },
    { to: "/skills", label: "Skills", icon: BookOpen },
    { to: "/allowlist", label: "Allowlist", icon: Shield },
    { to: "/settings", label: "Settings", icon: Settings2 },
    { to: "/logs", label: "Logs", icon: ScrollText },
    { to: "/help", label: "Help", icon: HelpCircle },
];

export default function App() {
    const [caps, setCaps] = useState<{
        version: string;
        channels: string[];
    } | null>(null);
    useEffect(() => {
        api.get("/capabilities")
            .then((r) => setCaps(r.data))
            .catch(() => {
                /* sidebar falls back to the static label */
            });
    }, []);
    return (
        <div
            className="flex min-h-screen bg-zinc-950 text-zinc-100"
            data-testid="comms-console"
        >
            <aside className="w-52 shrink-0 border-r border-zinc-800 bg-zinc-900/40 p-4">
                <div className="mb-6 flex items-center gap-2">
                    <InboxIcon className="h-5 w-5 text-amber-400" />
                    <div>
                        <div className="text-sm font-semibold">comms-mcp</div>
                        <div className="text-sm text-zinc-300">
                            {caps
                                ? `v${caps.version} · ${caps.channels.length} channels`
                                : "connecting…"}
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
                    <Route path="/inbox" element={<Inbox />} />
                    <Route path="/outbox" element={<Outbox />} />
                    <Route path="/chat" element={<Chat />} />
                    <Route path="/tools" element={<Tools />} />
                    <Route path="/skills" element={<Skills />} />
                    <Route path="/allowlist" element={<Allowlist />} />
                    <Route path="/settings" element={<Settings />} />
                    <Route path="/logs" element={<Logs />} />
                    <Route path="/help" element={<Help />} />
                </Routes>
            </main>
        </div>
    );
}

export { api };
