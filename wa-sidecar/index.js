/**
 * comms-mcp WhatsApp sidecar (baileys, v0.2).
 *
 * Links a WhatsApp number as a companion device. Exposes a tiny local REST
 * API for the Python server; inbound messages are forwarded to comms-mcp's
 * webhook (COMMS_INBOUND_WEBHOOK) where they are sanitized + stored.
 *
 * Env:
 *   WA_PORT              sidecar listen port (default 10709)
 *   COMMS_INBOUND_WEBHOOK comms-mcp inbound URL, e.g.
 *                         http://127.0.0.1:11028/api/v1/inbound/wa
 *
 * Pairing: start once, GET /qr (or /pairing) - scan with WhatsApp on the
 * phone (Linked devices). Auth persists in data/wa-auth/.
 */

import express from 'express';
import makeWASocket, {
    Browsers,
    DisconnectReason,
    useMultiFileAuthState,
} from '@whiskeysockets/baileys';
import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.WA_PORT || 10709);
const AUTH_DIR = path.join(__dirname, '..', 'data', 'wa-auth');
const INBOUND_WEBHOOK = process.env.COMMS_INBOUND_WEBHOOK || 'http://127.0.0.1:11028/api/v1/inbound/wa';

mkdirSync(AUTH_DIR, { recursive: true });

const state = {
    connection: 'connecting',
    latestQr: null,
    pairingCode: null,
    lastDisconnectReason: null,
};

async function forwardInbound(message) {
    const text =
        message?.message?.conversation ||
        message?.message?.extendedTextMessage?.text ||
        '';
    if (!text || !INBOUND_WEBHOOK) return;
    try {
        await fetch(INBOUND_WEBHOOK, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ from: message.key?.remoteJid || '?', text }),
        });
    } catch (err) {
        console.error('[wa-sidecar] inbound forward failed:', err.message);
    }
}

async function start() {
    const { state: auth, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const sock = makeWASocket({
        auth,
        printQRInTerminal: false,
        browser: Browsers.ubuntu('comms-mcp'),
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', (update) => {
        if (update.qr) state.latestQr = update.qr;
        if (update.pairingCode) state.pairingCode = update.pairingCode;
        if (update.connection) state.connection = update.connection;
        if (update.lastDisconnect?.error) {
            const reason = update.lastDisconnect.error.output?.statusCode;
            state.lastDisconnectReason = reason;
            if (reason === DisconnectReason.loggedOut) {
                state.latestQr = null;
                state.pairingCode = null;
            }
        }
        console.log('[wa-sidecar] connection:', state.connection);
    });

    sock.ev.on('messages.upsert', async ({ messages }) => {
        for (const m of messages) {
            if (!m.key?.fromMe) await forwardInbound(m);
        }
    });

    const app = express();
    app.use(express.json());

    app.get('/health', (_req, res) => {
        res.json({
            connected: state.connection === 'open',
            connection: state.connection,
            pairing_required: !state.latestQr && state.connection !== 'open',
            last_disconnect_reason: state.lastDisconnectReason ?? null,
        });
    });

    app.get('/qr', (_req, res) => {
        res.json({ qr: state.latestQr, pairing_code: state.pairingCode });
    });

    app.post('/send', async (req, res) => {
        const { to, text } = req.body || {};
        if (!to || !text) return res.status(400).json({ ok: false, error: 'to and text required' });
        if (state.connection !== 'open') {
            return res.status(503).json({ ok: false, error: `not connected (${state.connection})` });
        }
        const jid = `${to.replace(/[^\d]/g, '')}@s.whatsapp.net`;
        try {
            await sock.sendMessage(jid, { text: String(text).slice(0, 4000) });
            res.json({ ok: true, to: jid });
        } catch (err) {
            res.status(502).json({ ok: false, error: err.message });
        }
    });

    app.listen(PORT, () => console.log(`[wa-sidecar] listening on :${PORT}`));
}

start().catch((err) => {
    console.error('[wa-sidecar] fatal:', err);
    process.exit(1);
});

