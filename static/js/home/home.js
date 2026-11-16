// ── Demo photo dataset (fallback when no DB session exists) ──
const DEMO_PHOTOS = [
    { src: 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=600&auto=format&fit=crop&q=80', name: 'IMG_2024_001.jpg', size: '4.2 MB', dim: '4032 × 3024', date: 'Jun 12, 2024', bytes: 4.2 },
    { src: 'https://images.unsplash.com/photo-1501854140801-50d01698950b?w=600&auto=format&fit=crop&q=80', name: 'IMG_2024_002.jpg', size: '3.8 MB', dim: '4032 × 3024', date: 'Jun 13, 2024', bytes: 3.8 },
    { src: 'https://images.unsplash.com/photo-1470770903676-69b98201ea1c?w=600&auto=format&fit=crop&q=80', name: 'IMG_2024_003.jpg', size: '5.1 MB', dim: '4032 × 3024', date: 'Jun 14, 2024', bytes: 5.1 },
    { src: 'https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=600&auto=format&fit=crop&q=80', name: 'IMG_2024_004.jpg', size: '2.9 MB', dim: '3024 × 3024', date: 'Jun 15, 2024', bytes: 2.9 },
    { src: 'https://images.unsplash.com/photo-1518020382113-a7e8fc38eac9?w=600&auto=format&fit=crop&q=80', name: 'IMG_2024_005.jpg', size: '6.0 MB', dim: '4032 × 3024', date: 'Jun 16, 2024', bytes: 6.0 },
    { src: 'https://images.unsplash.com/photo-1475924156734-496f6cac6ec1?w=600&auto=format&fit=crop&q=80', name: 'IMG_2024_006.jpg', size: '3.3 MB', dim: '3024 × 3024', date: 'Jun 17, 2024', bytes: 3.3 },
    { src: 'https://images.unsplash.com/photo-1519681393784-d120267933ba?w=600&auto=format&fit=crop&q=80', name: 'IMG_2024_007.jpg', size: '4.7 MB', dim: '4032 × 3024', date: 'Jun 18, 2024', bytes: 4.7 },
    { src: 'https://images.unsplash.com/photo-1546587348-d12660c30c50?w=600&auto=format&fit=crop&q=80', name: 'IMG_2024_008.jpg', size: '2.2 MB', dim: '3024 × 3024', date: 'Jun 19, 2024', bytes: 2.2 },
];

// ── State ───────────────────────────────────────────────────
let PHOTOS = [...DEMO_PHOTOS];
let currentIndex = 0;
let keptCount = 0;
let trashedCount = 0;
let spaceClearedMB = 0;
let TOTAL = PHOTOS.length;
const history = [];  // { photo, action }
let decideUrl = null;
let undoUrl = null;
let finalizeUrl = null;
let pendingRequest = false;

function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

// ── DOM refs ────────────────────────────────────────────────
let card, img, imgName, imgMeta, imgDate, hintTrash, hintKeep, btnUndo;

document.addEventListener('DOMContentLoaded', () => {
    const sessionEl = document.getElementById('session-data');
    if (sessionEl) {
        const data = JSON.parse(sessionEl.textContent);
        PHOTOS = data.photos || [];
        TOTAL = data.total ?? PHOTOS.length;
        keptCount = data.kept_count ?? 0;
        trashedCount = data.trashed_count ?? 0;
        spaceClearedMB = data.space_cleared_mb ?? 0;
        decideUrl = data.decide_url || null;
        undoUrl = data.undo_url || null;
        finalizeUrl = data.finalize_url || null;
        if (Array.isArray(data.history)) {
            history.push(...data.history);
        }
    }

    card = document.getElementById('triage-card');
    img = document.getElementById('triage-img');
    imgName = document.getElementById('img-name');
    imgMeta = document.getElementById('img-meta');
    imgDate = document.getElementById('img-date');
    hintTrash = document.getElementById('hint-trash');
    hintKeep = document.getElementById('hint-keep');
    btnUndo = document.getElementById('btn-undo');

    if (card) {
        initDragEvents();
    }
    if (btnUndo) {
        btnUndo.disabled = history.length === 0;
    }
    updateUI();
    loadPhoto(0);
});

// ── Load photo ──────────────────────────────────────────────
function loadPhoto(idx) {
    if (!img) return;
    if (idx >= PHOTOS.length) { showDoneState(); return; }
    const p = PHOTOS[idx];
    img.src = p.src;
    imgName.textContent = p.name;
    imgMeta.textContent = `${p.size} · ${p.dim}`;
    imgDate.textContent = p.date;
}

// ── Handle decision ─────────────────────────────────────────
async function handleDecision(action) {
    if (pendingRequest || currentIndex >= PHOTOS.length) return;
    const photo = PHOTOS[currentIndex];

    if (decideUrl && photo.id) {
        pendingRequest = true;
        try {
            const resp = await fetch(decideUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify({ media_file_id: photo.id, decision: action }),
            });
            if (!resp.ok) return;
            const res = await resp.json();
            keptCount = res.kept_count;
            trashedCount = res.trashed_count;
            spaceClearedMB = res.space_cleared_mb;
        } finally {
            pendingRequest = false;
        }
    } else {
        if (action === 'trash') {
            trashedCount++;
            spaceClearedMB += photo.bytes;
        } else {
            keptCount++;
        }
    }

    // Animate card out
    card.classList.add(action === 'trash' ? 'swipe-left' : 'swipe-right');

    setTimeout(() => {
        card.classList.remove('swipe-left', 'swipe-right');
        history.push({ photo, action });
        currentIndex++;

        loadPhoto(currentIndex);
        updateUI();

        if (btnUndo) btnUndo.disabled = false;
    }, 350);
}

// ── Undo ─────────────────────────────────────────────────────
async function handleUndo() {
    if (pendingRequest || !history.length) return;

    if (undoUrl) {
        pendingRequest = true;
        try {
            const resp = await fetch(undoUrl, {
                method: 'POST',
                headers: { 'X-CSRFToken': getCsrfToken() },
            });
            if (!resp.ok) return;
            const res = await resp.json();
            history.pop();
            keptCount = res.kept_count;
            trashedCount = res.trashed_count;
            spaceClearedMB = res.space_cleared_mb;

            // If we were on the done state, reload to restore the card DOM cleanly.
            if (!document.getElementById('triage-card')) {
                window.location.reload();
                return;
            }
            PHOTOS.splice(currentIndex, 0, res.restored_photo);
            loadPhoto(currentIndex);
            updateUI();
            if (!history.length && btnUndo) btnUndo.disabled = true;
        } finally {
            pendingRequest = false;
        }
        return;
    }

    const last = history.pop();
    if (last.action === 'trash') {
        trashedCount--;
        spaceClearedMB -= last.photo.bytes;
    } else {
        keptCount--;
    }
    currentIndex--;
    loadPhoto(currentIndex);
    updateUI();

    if (!history.length && btnUndo) btnUndo.disabled = true;
}

// ── Update all UI counters ───────────────────────────────────
function updateUI() {
    const done = keptCount + trashedCount;
    const remaining = TOTAL - done;

    // Stats sidebar
    const filesRemainingEl = document.getElementById('files-remaining');
    const progressTextEl = document.getElementById('progress-text');
    const keepCountEl = document.getElementById('keep-count-text');
    const trashCountEl = document.getElementById('trash-count-text');
    if (filesRemainingEl) filesRemainingEl.textContent = remaining;
    if (progressTextEl) progressTextEl.textContent = `${done} / ${TOTAL}`;
    if (keepCountEl) keepCountEl.textContent = `✓ ${keptCount} kept`;
    if (trashCountEl) trashCountEl.textContent = `✗ ${trashedCount} trashed`;

    // Progress bar
    const pct = (done / TOTAL) * 100;
    const progressBar = document.getElementById('progress-bar');
    if (progressBar) progressBar.style.width = `${pct}%`;

    // Space cleared
    const mb = spaceClearedMB;
    const label = mb >= 1024 ? `${(mb / 1024).toFixed(1)} <span class="text-base font-semibold text-slate-400">GB</span>`
        : `${mb.toFixed(1)} <span class="text-base font-semibold text-slate-400">MB</span>`;
    const spaceClearedEl = document.getElementById('space-cleared');
    if (spaceClearedEl) spaceClearedEl.innerHTML = label;

    const spacePct = Math.min((mb / (15 * 1024)) * 100, 100);
    const bar = document.getElementById('space-bar');
    if (bar) {
        bar.style.setProperty('--target-w', `${spacePct}%`);
        bar.style.width = `${spacePct}%`;
    }

    // Trash count badge
    const trashBadge = document.getElementById('trash-count-badge');
    if (trashBadge) trashBadge.textContent = trashedCount;

    // Mobile remaining
    const mobileRem = document.getElementById('mobile-remaining');
    if (mobileRem) mobileRem.textContent = `${remaining} remaining`;

    // History list
    updateHistory();

    // Finalize modal values
    const modalTrashCount = document.getElementById('modal-trash-count');
    const modalSpace = document.getElementById('modal-space');
    if (modalTrashCount) modalTrashCount.textContent = `${trashedCount} file${trashedCount !== 1 ? 's' : ''}`;
    if (modalSpace) modalSpace.textContent = mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb.toFixed(1)} MB`;
}

// ── History list ─────────────────────────────────────────────
function updateHistory() {
    const list = document.getElementById('history-list');
    if (!list) return;
    list.innerHTML = '';

    if (!history.length) {
        list.innerHTML = `<li class="px-4 py-3 flex items-center gap-3 text-slate-400 text-xs italic">No decisions yet…</li>`;
        return;
    }

    // Show last 5 in reverse
    [...history].reverse().slice(0, 5).forEach(({ photo, action }) => {
        const isTrash = action === 'trash';
        const li = document.createElement('li');
        li.className = 'px-4 py-2.5 flex items-center gap-3';
        li.innerHTML = `
    <img src="${photo.src}" alt="" class="w-9 h-9 rounded-lg object-cover flex-shrink-0 border border-slate-100">
    <div class="flex-1 min-w-0">
        <p class="text-xs font-medium text-slate-700 truncate">${photo.name}</p>
        <p class="text-[10px] text-slate-400">${photo.size}</p>
    </div>
    <div class="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center ${isTrash ? 'bg-red-100' : 'bg-emerald-100'}">
        ${isTrash
                ? `<svg class="w-3 h-3 text-red-500" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>`
                : `<svg class="w-3 h-3 text-emerald-600" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>`
            }
    </div>
`;
        list.appendChild(li);
    });
}

// ── Done state ───────────────────────────────────────────────
function showDoneState() {
    const cardWrapper = document.getElementById('card-wrapper');
    if (cardWrapper) {
        cardWrapper.innerHTML = `
    <div class="flex flex-col items-center justify-center text-center rounded-3xl border-2 border-dashed border-slate-200 bg-slate-50 p-12 space-y-4" style="aspect-ratio: 3/4;">
        <div class="w-16 h-16 rounded-full bg-emerald-100 flex items-center justify-center">
            <svg class="w-8 h-8 text-emerald-600" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/>
            </svg>
        </div>
        <div>
            <p class="text-lg font-bold text-slate-900">All done! 🎉</p>
            <p class="text-sm text-slate-500 mt-1">You've triaged all ${TOTAL} photos.</p>
        </div>
    </div>
`;
    }

    const btnTrash = document.getElementById('btn-trash');
    const btnKeep = document.getElementById('btn-keep');
    if (btnTrash) {
        btnTrash.disabled = true;
        btnTrash.classList.add('opacity-40', 'cursor-not-allowed');
    }
    if (btnKeep) {
        btnKeep.disabled = true;
        btnKeep.classList.add('opacity-40', 'cursor-not-allowed');
    }
}

// ── Folder selection ─────────────────────────────────────────
function selectFolder(el) {
    document.querySelectorAll('.folder-item').forEach(b => {
        b.classList.remove('bg-slate-100', 'text-slate-900', 'font-medium');
        b.classList.add('text-slate-600');
    });
    el.classList.add('bg-slate-100', 'text-slate-900', 'font-medium');
    el.classList.remove('text-slate-600');
}

// ── Finalize modal ───────────────────────────────────────────
function handleFinalize() {
    document.getElementById('finalize-modal').classList.remove('hidden');
}
function closeModal() {
    document.getElementById('finalize-modal').classList.add('hidden');
}

// ── New session modal ────────────────────────────────────────
function openNewSessionModal() {
    const modal = document.getElementById('new-session-modal');
    if (modal) {
        modal.classList.remove('hidden');
        const input = document.getElementById('new-folder-name');
        if (input) input.focus();
    }
}
function closeNewSessionModal() {
    const modal = document.getElementById('new-session-modal');
    if (modal) modal.classList.add('hidden');
}
function showToast(message) {
    const existing = document.getElementById('cull-toast');
    if (existing) existing.remove();
    const toast = document.createElement('div');
    toast.id = 'cull-toast';
    toast.className = 'fixed bottom-5 right-5 z-50 bg-slate-900 text-white text-xs font-medium px-4 py-3 rounded-xl shadow-lg border border-slate-700 flex items-center gap-2 transition-opacity duration-300';
    toast.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400 flex-shrink-0"></span><span>${message}</span>`;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

async function confirmFinalize() {
    if (pendingRequest) return;
    closeModal();

    if (finalizeUrl) {
        pendingRequest = true;
        try {
            const resp = await fetch(finalizeUrl, {
                method: 'POST',
                headers: { 'X-CSRFToken': getCsrfToken() },
            });
            if (!resp.ok) return;
            const res = await resp.json();
            TOTAL = res.total;
            keptCount = res.kept_count;
            trashedCount = res.trashed_count;
            spaceClearedMB = res.space_cleared_mb;
            for (let i = history.length - 1; i >= 0; i--) {
                if (history[i].action === 'trash') history.splice(i, 1);
            }
            if (btnUndo) btnUndo.disabled = history.length === 0;
            updateUI();
            if (res.remaining === 0) showDoneState();
            showToast(`Cleanup complete: ${res.deleted_count} file${res.deleted_count !== 1 ? 's' : ''} removed (${res.freed_mb.toFixed(1)} MB freed).`);
        } finally {
            pendingRequest = false;
        }
        return;
    }

    setTimeout(() => {
        showToast(`Cleanup complete: ${trashedCount} file${trashedCount !== 1 ? 's' : ''} removed (${spaceClearedMB.toFixed(1)} MB freed).`);
        trashedCount = 0;
        spaceClearedMB = 0;
        updateUI();
    }, 100);
}

// ── Keyboard shortcuts ───────────────────────────────────────
document.addEventListener('keydown', e => {
    const tag = e.target && e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    if (e.key === 'ArrowLeft') handleDecision('trash');
    if (e.key === 'ArrowRight') handleDecision('keep');
    if ((e.key === 'z' || e.key === 'Z') && (e.metaKey || e.ctrlKey)) { e.preventDefault(); handleUndo(); }
});

// ── Drag-to-swipe on card ────────────────────────────────────
function initDragEvents() {
    let startX = 0, dragging = false;

    card.addEventListener('mousedown', e => { startX = e.clientX; dragging = true; });
    card.addEventListener('mousemove', e => {
        if (!dragging) return;
        const dx = e.clientX - startX;
        card.style.transform = `translateX(${dx * 0.3}px) rotate(${dx * 0.02}deg)`;

        if (dx < -30) { hintTrash.style.opacity = '1'; hintKeep.style.opacity = '0'; }
        else if (dx > 30) { hintKeep.style.opacity = '1'; hintTrash.style.opacity = '0'; }
        else { hintTrash.style.opacity = '0'; hintKeep.style.opacity = '0'; }
    });
    document.addEventListener('mouseup', e => {
        if (!dragging) return;
        dragging = false;
        const dx = e.clientX - startX;
        card.style.transform = '';
        if (hintTrash) hintTrash.style.opacity = '0';
        if (hintKeep) hintKeep.style.opacity = '0';

        if (dx < -60) handleDecision('trash');
        else if (dx > 60) handleDecision('keep');
    });

    // Touch support
    card.addEventListener('touchstart', e => { startX = e.touches[0].clientX; dragging = true; }, { passive: true });
    card.addEventListener('touchmove', e => {
        if (!dragging) return;
        const dx = e.touches[0].clientX - startX;
        card.style.transform = `translateX(${dx * 0.3}px) rotate(${dx * 0.02}deg)`;
        if (dx < -30) { hintTrash.style.opacity = '1'; hintKeep.style.opacity = '0'; }
        else if (dx > 30) { hintKeep.style.opacity = '1'; hintTrash.style.opacity = '0'; }
        else { hintTrash.style.opacity = '0'; hintKeep.style.opacity = '0'; }
    }, { passive: true });
    card.addEventListener('touchend', e => {
        if (!dragging) return;
        dragging = false;
        const dx = e.changedTouches[0].clientX - startX;
        card.style.transform = '';
        if (hintTrash) hintTrash.style.opacity = '0';
        if (hintKeep) hintKeep.style.opacity = '0';
        if (dx < -60) handleDecision('trash');
        else if (dx > 60) handleDecision('keep');
    });
}
