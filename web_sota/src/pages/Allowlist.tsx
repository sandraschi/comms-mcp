import { Shield, Copy } from 'lucide-react';
import { useStatus } from '../App';

export default function Allowlist() {
    const { status } = useStatus();
    const allow = status?.allowlist ?? [];

    const copy = () => {
        navigator.clipboard.writeText(allow.join(','));
    };

    return (
        <div data-testid="allowlist-page">
            <h1 className="text-2xl font-bold">Allowlist</h1>
            <p className="mt-1 text-sm text-zinc-500">
                Send is blocked outside this chat-id list (server-enforced).
            </p>

            <div className="mt-4 rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
                <div className="flex items-center justify-between">
                    <h2 className="flex items-center gap-2 text-sm font-semibold text-zinc-200">
                        <Shield className="h-4 w-4 text-amber-400" /> Configured chats
                    </h2>
                    <button
                        onClick={copy}
                        className="flex items-center gap-1.5 rounded-lg border border-zinc-800 px-2 py-1 text-xs text-zinc-400 hover:text-white"
                    >
                        <Copy className="h-3 w-3" /> copy
                    </button>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                    {allow.length === 0 && <div className="text-sm text-zinc-600">empty — set COMMS_TELEGRAM_CHAT_IDS</div>}
                    {allow.map((id) => (
                        <span key={id} className="rounded-lg border border-zinc-700 bg-zinc-800/60 px-3 py-1.5 font-mono text-xs text-zinc-300">
                            {id}
                        </span>
                    ))}
                </div>
            </div>

            <div className="mt-4 rounded-xl border border-zinc-800 bg-zinc-900/20 p-4 text-xs text-zinc-600">
                The allowlist is configuration, not state: edit <code className="text-zinc-400">COMMS_TELEGRAM_CHAT_IDS</code>{' '}
                in <code className="text-zinc-400">.env</code> (comma-separated) and restart the backend. To find your chat id,
                message the bot and check <code className="text-zinc-400">read_recent</code>.
            </div>
        </div>
    );
}

