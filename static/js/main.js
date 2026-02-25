// === Time display ===
function updateTime() {
    const el = document.getElementById('topbar-time');
    if (el) {
        el.textContent = new Date().toLocaleTimeString('en-US', { hour12: false });
    }
}
updateTime();
setInterval(updateTime, 1000);

// === Confirm Modal ===
let _confirmCallback = null;

function showConfirmModal(title, message, command, callback, btnText, btnClass) {
    document.getElementById('modal-title').textContent = title || 'Confirm Action';
    document.getElementById('modal-message').textContent = message || 'Are you sure?';

    const codeBlock = document.getElementById('modal-code-block');
    if (command) {
        codeBlock.style.display = 'block';
        document.getElementById('modal-code').textContent = command;
    } else {
        codeBlock.style.display = 'none';
    }

    const btn = document.getElementById('modal-confirm-btn');
    btn.textContent = btnText || 'Confirm';
    btn.className = `btn btn--${btnClass || 'danger'}`;

    _confirmCallback = callback;
    document.getElementById('confirmModal').style.display = 'flex';
}

function closeConfirmModal() {
    document.getElementById('confirmModal').style.display = 'none';
    _confirmCallback = null;
}

document.getElementById('modal-confirm-btn').addEventListener('click', function () {
    if (_confirmCallback) _confirmCallback();
    closeConfirmModal();
});

document.getElementById('confirmModal').addEventListener('click', function (e) {
    if (e.target === this) closeConfirmModal();
});

// === CSRF Helper ===
function getCsrfToken() {
    const meta = document.querySelector('meta[name=csrfmiddlewaretoken]');
    if (meta) return meta.content;
    const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
    return cookie ? cookie.split('=')[1].trim() : '';
}

// === Generic POST ===
async function postJson(url, data) {
    const res = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken(),
        },
        body: JSON.stringify(data),
    });
    return res.json();
}

// === Format duration ===
function formatDuration(seconds) {
    if (seconds === null || seconds === undefined) return '—';
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return `${m}m ${s}s`;
}

// === Format relative time ===
function timeAgo(dateStr) {
    if (!dateStr) return '—';
    const d = new Date(dateStr);
    const diff = Math.floor((Date.now() - d.getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

// === Notification toast ===
function showToast(message, type) {
    const container = document.querySelector('.messages-container') || (() => {
        const c = document.createElement('div');
        c.className = 'messages-container';
        document.querySelector('.content').prepend(c);
        return c;
    })();

    const alert = document.createElement('div');
    alert.className = `alert alert--${type || 'info'}`;
    alert.innerHTML = `<span>${message}</span><button onclick="this.parentElement.remove()">×</button>`;
    container.appendChild(alert);
    setTimeout(() => alert.remove(), 5000);
}

// === Run Scraper ===
function runScraper(subId, mainId, name, command) {
    showConfirmModal(
        'Run Scraper',
        `Start "${name}" now?`,
        command,
        async () => {
            const btn = document.getElementById(`run-btn-${subId}`);
            if (btn) { btn.disabled = true; btn.innerHTML = '<div class="spinner"></div>'; }

            try {
                const res = await fetch(`/scrapers/${mainId}/sub/${subId}/run/`, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': getCsrfToken() },
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    showToast(`Scraper "${name}" started`, 'success');
                    setTimeout(() => location.reload(), 1500);
                } else {
                    showToast(data.message || 'Failed to start', 'error');
                    if (btn) { btn.disabled = false; btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polygon points="5 3 19 12 5 21 5 3"/></svg> Run'; }
                }
            } catch (e) {
                showToast('Network error', 'error');
                if (btn) { btn.disabled = false; }
            }
        },
        'Run Now', 'success'
    );
}

// === Stop Scraper ===
function stopScraper(subId, mainId, name, pid) {
    showConfirmModal(
        'Stop Scraper',
        `Stop "${name}" (PID: ${pid})?`,
        `kill -TERM ${pid}`,
        async () => {
            try {
                const res = await fetch(`/scrapers/${mainId}/sub/${subId}/stop/`, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': getCsrfToken() },
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    showToast(`Process stopped`, 'success');
                    setTimeout(() => location.reload(), 1000);
                } else {
                    showToast(data.message || 'Failed to stop', 'error');
                }
            } catch (e) {
                showToast('Network error', 'error');
            }
        },
        'Stop Process', 'danger'
    );
}
