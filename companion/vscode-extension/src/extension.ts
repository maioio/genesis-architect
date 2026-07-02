/**
 * Genesis PRO Companion — VS Code Extension (MVP)
 *
 * Sends cursor position (file + line) to the genesis-core sidecar
 * via HTTP POST to localhost:47292/ide-event.
 *
 * Data sent: { file, line, event } — NEVER file contents.
 * Silent if the sidecar is not running.
 */

import * as vscode from 'vscode';
import * as http from 'http';

const SIDECAR_PORT = 47292;
const RATE_LIMIT_MS = 3000; // max one event per 3 seconds per file

let lastEventTime: number = 0;
let lastFile: string = '';
let lastLine: number = -1;

function postEvent(file: string, line: number, event: string): void {
    const now = Date.now();
    // Rate limit: suppress if same location within window
    if (file === lastFile && line === lastLine && now - lastEventTime < RATE_LIMIT_MS) {
        return;
    }
    lastEventTime = now;
    lastFile = file;
    lastLine = line;

    const body = JSON.stringify({ file, line, event });
    const options: http.RequestOptions = {
        hostname: '127.0.0.1',
        port: SIDECAR_PORT,
        path: '/ide-event',
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(body),
        },
    };

    const req = http.request(options);
    req.on('error', () => { /* sidecar not running — silent */ });
    req.setTimeout(500, () => req.destroy());
    req.write(body);
    req.end();
}

export function activate(ctx: vscode.ExtensionContext): void {
    // Cursor movement → send (file, line) to sidecar
    ctx.subscriptions.push(
        vscode.window.onDidChangeTextEditorSelection((e) => {
            const file = e.textEditor.document.fileName;
            const line = e.selections[0].active.line + 1; // 1-based
            postEvent(file, line, 'cursor');
        })
    );

    // File open → notify sidecar
    ctx.subscriptions.push(
        vscode.window.onDidChangeActiveTextEditor((editor) => {
            if (!editor) return;
            const file = editor.document.fileName;
            const line = editor.selection.active.line + 1;
            postEvent(file, line, 'open');
        })
    );
}

export function deactivate(): void {}
