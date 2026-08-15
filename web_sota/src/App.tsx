import { useEffect, useState } from 'react';
import { NavLink, Route, Routes } from 'react-router-dom';
import { Send, Inbox, Shield, HelpCircle, LayoutDashboard } from 'lucide-react';
import axios from 'axios';
import Dashboard from './pages/Dashboard';
import Outbox from './pages/Outbox';
import Allowlist from './pages/Allowlist';
import Help from './pages/Help';

const api = axios.create({ baseURL: '/api', timeout: 10000 });

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
            const r = await api.get('/v1/status');
            setStatus(r.data);
        } catch {
            setStatus(null);
        }
    };
    useEffect(() => {
        refresh();
        const t = setInterval(refresh, 15000);
        return () => clearInterval(t);
    }, []);
    return { status, refresh };
};

const NAV = [
    { to: '/', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/outbox', label: 'Outbox', icon: Send },
    { to: '/allowlist', label: 'Allowlist', icon: Shield },
    { to: '/help', label: 'Help', icon: HelpCircle },
];

export default function App() {
    return (
        <div className="flex min-h-screen bg-zinc-950 text-zinc-100" data-testid="comms-console">
            <aside className="w-52 shrink-0 border-r border-zinc-800 bg-zinc-900/40 p-4">
                <div className="mb-6 flex items-center gap-2">
                    <Inbox className="h-5 w-5 text-amber-400" />
                    <div>
                        <div className="text-sm font-semibold">comms-mcp</div>
                        <div className="text-[10px] text-zinc-500">v0.1 · telegram</div>
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
                                        ? 'bg-amber-500/10 text-amber-300'
                                        : 'text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200'
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

