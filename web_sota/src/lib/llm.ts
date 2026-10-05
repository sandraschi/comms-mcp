import { api } from "../App";

export interface LlmProvider {
    id: string;
    label: string;
    kind: "local" | "cloud";
    base_url: string;
    needs_key: boolean;
    key_env: string | null;
    configured: boolean;
    detected: boolean;
    models: string[];
    note: string;
}

export interface GpuInfo {
    index: number;
    name: string;
    total_mb: number;
    used_mb: number;
    free_mb: number;
}

export interface ChatMessage {
    role: "user" | "assistant" | "system";
    content: string;
}

export const getProviders = async (): Promise<LlmProvider[]> => {
    const r = await api.get("/llm/providers");
    return r.data.providers;
};

export const getModels = async (
    provider: string,
): Promise<{ models: string[]; source: string }> => {
    const r = await api.get("/llm/models", { params: { provider } });
    return r.data;
};

export const getGpus = async (): Promise<GpuInfo[]> => {
    const r = await api.get("/llm/gpus");
    return r.data.gpus;
};

export const saveCloudKey = async (
    provider: string,
    api_key: string,
): Promise<void> => {
    // Key travels in the POST body only; never stored in localStorage.
    await api.post("/settings/llm", { provider, api_key, select: false });
};

export const clearCloudKey = async (provider: string): Promise<void> => {
    await api.delete("/settings/llm/key", { params: { provider } });
};

/**
 * Stream a chat completion through the backend proxy (never direct to a
 * provider). Parses OpenAI-style `data:` SSE chunks. Yields content deltas.
 */
export async function* streamChat(
    provider: string,
    model: string,
    messages: ChatMessage[],
): AsyncGenerator<string, void, unknown> {
    const res = await fetch("/api/llm/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider, model, messages }),
    });
    if (!res.ok || !res.body) {
        throw new Error(`stream failed: ${res.status}`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
            if (!line.startsWith("data:")) continue;
            const payload = line.slice(5).trim();
            if (payload === "[DONE]") return;
            try {
                const data = JSON.parse(payload);
                if (data.error) throw new Error(String(data.error));
                const piece = data.choices?.[0]?.delta?.content;
                if (piece) yield piece;
            } catch (err) {
                if (err instanceof Error && err.message) throw err;
            }
        }
    }
}
