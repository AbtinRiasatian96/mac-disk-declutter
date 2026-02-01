// Mac Disk Declutter — Frontend

const API = '';
let scanResults = [];
let selectedPaths = new Set();

// --- Helpers ---
function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }
function humanSize(bytes) {
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    let b = bytes;
    while (b >= 1024 && i < units.length - 1) { b /= 1024; i++; }
    return b.toFixed(1) + ' ' + units[i];
}
function safetyIcon(category) {
    return { safe: '\u{1F7E2}', review: '\u{1F7E1}', personal: '\u{1F535}' }[category] || '\u26AA';
}
function typeIcon(type) {
    return type === 'folder' ? '\u{1F4C1}' : '\u{1F4C4}';
}

// --- Scan ---
$('#btn-scan').addEventListener('click', async () => {
    const btn = $('#btn-scan');
    const status = $('#scan-status');
    btn.disabled = true;
    status.innerHTML = '<span class="spinner"></span> Scanning and analyzing...';

    try {
        const resp = await fetch(API + '/api/scan', { method: 'POST' });
        const data = await resp.json();
        scanResults = data.items;
        renderResults();
        $('#scan-section').querySelector('.status-text').textContent =
            `Found ${data.count} items`;
        $('#results-section').classList.remove('hidden');
    } catch (e) {
        status.textContent = 'Scan failed: ' + e.message;
    }
    btn.disabled = false;
});

// --- Render Results ---
function renderResults() {
    const list = $('#results-list');
    list.innerHTML = '';
    selectedPaths.clear();
    updateTotal();

    scanResults.forEach((item, idx) => {
        const row = document.createElement('div');
        row.className = 'result-item';
        row.innerHTML = `
            <input type="checkbox" data-idx="${idx}" data-path="${item.path}" data-size="${item.size}">
            <span class="item-icon">${typeIcon(item.type)}</span>
            <div class="item-info">
                <div class="item-name" title="${item.path}">${item.name}</div>
                <div class="item-desc">${item.description || ''} ${item.consequence ? '— ' + item.consequence : ''}</div>
            </div>
            <div class="item-meta">
                <span class="item-size">${item.size_human}</span>
                <span class="item-safety" title="Safety: ${item.safety_score || '?'}/100">${safetyIcon(item.category)}</span>
                <button class="item-ask" data-name="${item.name}" title="Ask about this">?</button>
            </div>
        `;
        list.appendChild(row);
    });

    // Checkbox listeners
    list.querySelectorAll('input[type=checkbox]').forEach(cb => {
        cb.addEventListener('change', () => {
            if (cb.checked) selectedPaths.add(cb.dataset.path);
            else selectedPaths.delete(cb.dataset.path);
            updateTotal();
        });
    });

    // Ask buttons
    list.querySelectorAll('.item-ask').forEach(btn => {
        btn.addEventListener('click', () => {
            openChat();
            const name = btn.dataset.name;
            $('#chat-input').value = `What is "${name}" and is it safe to delete?`;
            $('#chat-input').focus();
        });
    });
}

function updateTotal() {
    let total = 0;
    $$('#results-list input[type=checkbox]:checked').forEach(cb => {
        total += parseInt(cb.dataset.size) || 0;
    });
    $('#space-total').textContent = 'Space to free: ' + humanSize(total);
    $('#btn-delete').disabled = selectedPaths.size === 0;
}

// --- Select All ---
$('#select-all').addEventListener('change', (e) => {
    $$('#results-list input[type=checkbox]').forEach(cb => {
        cb.checked = e.target.checked;
        if (cb.checked) selectedPaths.add(cb.dataset.path);
        else selectedPaths.delete(cb.dataset.path);
    });
    updateTotal();
});

// --- Delete ---
$('#btn-delete').addEventListener('click', () => {
    if (selectedPaths.size === 0) return;
    const method = $('#delete-method').value;
    const label = method === 'trash' ? 'move to Trash' : 'permanently delete';
    $('#confirm-text').textContent =
        `Are you sure you want to ${label} ${selectedPaths.size} item(s)?` +
        (method === 'permanent' ? ' This cannot be undone!' : '');
    $('#confirm-modal').classList.remove('hidden');
});

$('#btn-confirm-yes').addEventListener('click', async () => {
    $('#confirm-modal').classList.add('hidden');
    const method = $('#delete-method').value;
    const paths = [...selectedPaths];

    try {
        const resp = await fetch(API + '/api/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ paths, method }),
        });
        const data = await resp.json();
        const ok = data.success?.length || 0;
        const fail = data.failed?.length || 0;

        // Remove deleted items from local state
        const deleted = new Set(data.success || []);
        scanResults = scanResults.filter(i => !deleted.has(i.path));
        renderResults();

        const status = $('#scan-status');
        status.textContent = `Deleted ${ok} item(s)` + (fail ? `, ${fail} failed` : '');
    } catch (e) {
        alert('Delete failed: ' + e.message);
    }
});

// --- Settings ---
$('#btn-settings').addEventListener('click', async () => {
    try {
        const resp = await fetch(API + '/api/settings');
        const cfg = await resp.json();
        $('#set-provider').value = cfg.llm_provider || 'claude';
        $('#set-claude-model').value = cfg.claude_model || '';
        $('#set-ollama-model').value = cfg.ollama_model || '';
        $('#set-ollama-url').value = cfg.ollama_url || '';
        toggleProviderSettings(cfg.llm_provider);
    } catch(e) {}
    $('#settings-modal').classList.remove('hidden');
});

$('#set-provider').addEventListener('change', (e) => toggleProviderSettings(e.target.value));

function toggleProviderSettings(provider) {
    $('#claude-settings').classList.toggle('hidden', provider !== 'claude');
    $('#ollama-settings').classList.toggle('hidden', provider !== 'ollama');
}

$('#btn-save-settings').addEventListener('click', async () => {
    const settings = {
        llm_provider: $('#set-provider').value,
        claude_api_key: $('#set-claude-key').value || undefined,
        claude_model: $('#set-claude-model').value,
        ollama_model: $('#set-ollama-model').value,
        ollama_url: $('#set-ollama-url').value,
    };
    try {
        await fetch(API + '/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings),
        });
        $('#settings-modal').classList.add('hidden');
    } catch(e) {
        alert('Failed to save: ' + e.message);
    }
});

// --- Chat ---
function openChat() {
    $('#chat-sidebar').classList.remove('hidden');
}

$('#btn-chat').addEventListener('click', openChat);

$('#btn-send-chat').addEventListener('click', sendChat);
$('#chat-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') sendChat(); });

async function sendChat() {
    const input = $('#chat-input');
    const msg = input.value.trim();
    if (!msg) return;
    input.value = '';

    appendChatMsg('user', msg);

    const selected = [...selectedPaths].map(p => {
        const item = scanResults.find(i => i.path === p);
        return item ? item.name : p;
    });

    try {
        const resp = await fetch(API + '/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: msg, selected_items: selected }),
        });
        const data = await resp.json();
        appendChatMsg('assistant', data.reply);
    } catch(e) {
        appendChatMsg('assistant', 'Error: ' + e.message);
    }
}

function appendChatMsg(role, text) {
    const container = $('#chat-messages');
    const div = document.createElement('div');
    div.className = 'chat-msg ' + role;
    div.textContent = text;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

// --- Close buttons ---
document.querySelectorAll('[data-close]').forEach(btn => {
    btn.addEventListener('click', () => {
        document.getElementById(btn.dataset.close).classList.add('hidden');
    });
});
