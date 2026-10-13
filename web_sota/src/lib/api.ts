// Backend base URL. In dev it is empty so the Vite proxy handles /api.
// In production (Tauri webview or static serve) it must be absolute: the
// webview origin is tauri://localhost, so a relative /api would hit the
// webview, not the operator backend on 11238. See TAURI_PRODUCTION_PITFALLS.md.
export const API_BASE: string = import.meta.env.DEV
    ? ""
    : "http://127.0.0.1:11238";

export function apiUrl(path: string): string {
    return `${API_BASE}${path}`;
}
