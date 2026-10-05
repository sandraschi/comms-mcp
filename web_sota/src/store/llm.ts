import { create } from "zustand";
import {
    type GpuInfo,
    getGpus,
    getModels,
    getProviders,
    type LlmProvider,
} from "../lib/llm";

const LS_PROVIDER = "llm_provider";
const LS_MODEL = "llm_model";
const LS_GPU = "llm_gpu";

interface LlmState {
    probing: boolean;
    providers: LlmProvider[];
    models: string[];
    modelsSource: string;
    gpus: GpuInfo[];
    selectedProvider: string;
    selectedModel: string;
    targetGpu: number;
    error: string | null;
    detect: () => Promise<void>;
    selectProvider: (id: string) => Promise<void>;
    selectModel: (model: string) => void;
    selectGpu: (index: number) => void;
}

/** Best local model: prefer an already-loaded one, else first installed. */
function pickModel(models: string[]): string {
    const saved = localStorage.getItem(LS_MODEL);
    if (saved && models.includes(saved)) return saved;
    return models[0] ?? "";
}

export const useLlm = create<LlmState>((set, get) => ({
    probing: false,
    providers: [],
    models: [],
    modelsSource: "",
    gpus: [],
    selectedProvider: localStorage.getItem(LS_PROVIDER) ?? "",
    selectedModel: localStorage.getItem(LS_MODEL) ?? "",
    targetGpu: Number(localStorage.getItem(LS_GPU) ?? "0"),
    error: null,

    detect: async () => {
        set({ probing: true, error: null });
        try {
            const [providers, gpus] = await Promise.all([
                getProviders(),
                getGpus(),
            ]);
            const detectedLocals = providers.filter(
                (p) => p.kind === "local" && p.detected,
            );
            const saved = localStorage.getItem(LS_PROVIDER);
            let chosen =
                saved && providers.find((p) => p.id === saved && p.configured)
                    ? saved
                    : (detectedLocals[0]?.id ?? "");
            if (!chosen) {
                const configuredCloud = providers.find(
                    (p) => p.kind === "cloud" && p.configured,
                );
                chosen = configuredCloud?.id ?? "";
            }
            // dual-NVIDIA: default to the secondary card (index > 0)
            const savedGpu = Number(localStorage.getItem(LS_GPU) ?? "-1");
            const targetGpu =
                gpus.length > 1
                    ? (gpus.find((g) => g.index === savedGpu)?.index ??
                      gpus.find((g) => g.index > 0)?.index ??
                      0)
                    : 0;
            set({
                providers,
                gpus,
                selectedProvider: chosen || get().selectedProvider,
                targetGpu,
                probing: false,
            });
            if (chosen) await get().selectProvider(chosen);
        } catch (err) {
            set({
                probing: false,
                error: err instanceof Error ? err.message : "detect failed",
            });
        }
    },

    selectProvider: async (id: string) => {
        localStorage.setItem(LS_PROVIDER, id);
        set({ selectedProvider: id });
        const provider = get().providers.find((p) => p.id === id);
        // Locals already carry their model list from the probe; clouds fetch live.
        let models = provider?.models ?? [];
        let source = models.length ? "live" : "";
        if (!models.length) {
            try {
                const r = await getModels(id);
                models = r.models;
                source = r.source;
            } catch {
                models = [];
                source = "";
            }
        }
        const model = pickModel(models);
        localStorage.setItem(LS_MODEL, model);
        set({ models, modelsSource: source, selectedModel: model });
    },

    selectModel: (model: string) => {
        localStorage.setItem(LS_MODEL, model);
        set({ selectedModel: model });
    },

    selectGpu: (index: number) => {
        localStorage.setItem(LS_GPU, String(index));
        set({ targetGpu: index });
    },
}));
