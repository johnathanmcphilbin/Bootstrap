// No credentials here — uploads go through /api/upload-url on the server

// ── LEADERBOARD ─────────────────────────────────────────────────────────────
const TIER_COLORS = {
  'Funded': '#f5a623',
  'Series A': '#aaaaaa',
  'Pre-seed': '#8b5c2a',
  'Bootstrapped': '#00c805',
  'pending': '#3d3a36',
};

async function fetchLeaderboard() {
  try {
    const res = await fetch('/api/leaderboard');
    const data = await res.json();
    renderLeaderboard(data.leaderboard || []);
  } catch (e) {
    const el = document.getElementById('leaderboard-body');
    if (el) el.innerHTML = '<p style="color:#c0392b;font-family:Inter,sans-serif;font-size:13px;padding:24px 0;">Failed to load leaderboard. Please try again later.</p>';
  }
}

function renderLeaderboard(entries) {
  const el = document.getElementById('leaderboard-body');
  if (!el) return;
  if (!entries.length) {
    el.innerHTML = '<p style="color:#6b6560;font-family:Inter,sans-serif;font-size:13px;padding:24px 0;">No shipped projects yet. Be the first.</p>';
    return;
  }
  el.innerHTML = entries.map(e => {
    const color = TIER_COLORS[e.tier] || '#6b6560';
    const rankColor = e.rank === 1 ? '#f5a623' : e.rank === 2 ? '#aaaaaa' : e.rank === 3 ? '#8b5c2a' : '#6b6560';
    return `
      <div style="display:flex;align-items:center;gap:16px;padding:16px 0;border-bottom:1px solid #2a2825;">
        <div style="font-size:13px;font-weight:700;color:${rankColor};min-width:36px;">#${e.rank}</div>
        <div style="flex:1;min-width:0;">
          <div style="font-family:'Alfa Slab One',serif;font-size:17px;color:#f0ede8;margin-bottom:2px;">${e.project_name}</div>
          <div style="font-size:11px;color:#6b6560;">by ${e.builder_name}</div>
        </div>
        <div style="display:flex;gap:10px;font-size:11px;">
          ${e.live_url ? `<a href="${e.live_url}" target="_blank" style="color:#f5a623;text-decoration:none;">Live →</a>` : ''}
          ${e.github_url ? `<a href="${e.github_url}" target="_blank" style="color:#6b6560;text-decoration:none;">GitHub</a>` : ''}
        </div>
        <div style="text-align:right;min-width:80px;">
          <div style="font-size:20px;font-weight:700;color:#f0ede8;">${e.score}</div>
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:${color};">${e.tier}</div>
        </div>
      </div>
    `;
  }).join('');
}

// ── FILE UPLOAD ──────────────────────────────────────────────────────────────
function setupUploadZone(zoneId, fileInputId, hiddenInputId, bucket, maxMB) {
  const zone = document.getElementById(zoneId);
  const fileInput = document.getElementById(fileInputId);
  const hiddenInput = document.getElementById(hiddenInputId);
  const progress = zone.querySelector('.upload-progress');
  if (!zone) return;

  zone.addEventListener('click', () => fileInput.click());

  zone.addEventListener('dragover', e => {
    e.preventDefault();
    zone.classList.add('drag-over');
  });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file, zone, hiddenInput, progress, bucket, maxMB);
  });
  fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    if (file) handleUpload(file, zone, hiddenInput, progress, bucket, maxMB);
  });
}

async function handleUpload(file, zone, hiddenInput, progress, bucket, maxMB) {
  const maxBytes = maxMB * 1024 * 1024;
  if (file.size > maxBytes) {
    progress.style.color = '#c0392b';
    progress.textContent = `file too large (max ${maxMB}mb)`;
    return;
  }

  zone.classList.remove('done');
  progress.style.color = '#f5a623';
  progress.textContent = 'getting upload url...';

  // Step 1: ask server for a signed upload URL (no credentials in client)
  let signedUrl, publicUrl;
  try {
    const res = await fetch('/api/upload-url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        bucket,
        content_type: file.type,
        file_size: file.size,
        filename: file.name,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      progress.style.color = '#c0392b';
      progress.textContent = data.error || 'failed to get upload url';
      return;
    }
    signedUrl = data.signed_url;
    publicUrl = data.public_url;
  } catch (e) {
    progress.style.color = '#c0392b';
    progress.textContent = 'network error getting upload url';
    return;
  }

  // Step 2: upload directly to Supabase Storage using the signed URL
  progress.textContent = 'uploading...';
  try {
    const uploadRes = await fetch(signedUrl, {
      method: 'PUT',
      headers: { 'Content-Type': file.type },
      body: file,
    });
    if (!uploadRes.ok) {
      progress.style.color = '#c0392b';
      progress.textContent = 'upload failed (' + uploadRes.status + ')';
      return;
    }
  } catch (e) {
    progress.style.color = '#c0392b';
    progress.textContent = 'upload failed — network error';
    return;
  }

  hiddenInput.value = publicUrl;
  zone.classList.add('done');
  progress.style.color = '#00c805';
  progress.textContent = '✓ ' + file.name;
  const label = zone.querySelector('.upload-label');
  if (label) label.textContent = file.name;
}

// ── SUBMIT ───────────────────────────────────────────────────────────────────
async function submitProject(e) {
  e.preventDefault();
  const form = document.getElementById('submit-form');
  const btn = document.getElementById('submit-btn');
  const msg = document.getElementById('submit-msg');

  const pitchUrl = document.getElementById('pitch_url_val').value;
  if (!pitchUrl) {
    msg.style.color = '#c0392b';
    msg.textContent = 'Please upload your demo video first.';
    return;
  }

  const payload = {
    project_name: form.project_name.value.trim(),
    builder_name: form.builder_name.value.trim(),
    live_url: form.live_url.value.trim(),
    github_url: form.github_url.value.trim(),
    pitch_url: pitchUrl,
    deck_url: document.getElementById('deck_url_val').value || null,
  };

  btn.disabled = true;
  btn.textContent = 'submitting...';
  msg.textContent = '';

  try {
    const res = await fetch('/api/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (res.ok) {
      msg.style.color = '#00c805';
      msg.textContent = "submitted! we'll review it soon.";
      form.reset();
      document.querySelectorAll('.upload-zone').forEach(z => {
        z.classList.remove('done');
        z.querySelector('.upload-progress').textContent = '';
      });
      document.getElementById('pitch_url_val').value = '';
      document.getElementById('deck_url_val').value = '';
    } else {
      msg.style.color = '#c0392b';
      msg.textContent = data.error || 'submission failed.';
    }
  } catch (err) {
    msg.style.color = '#c0392b';
    msg.textContent = 'network error. please try again.';
  } finally {
    btn.disabled = false;
    btn.textContent = 'ship it';
  }
}

// ── INIT ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  fetchLeaderboard();

  setupUploadZone('video-drop', 'video-file-input', 'pitch_url_val', 'videos', 200);
  setupUploadZone('deck-drop', 'deck-file-input', 'deck_url_val', 'decks', 20);

  const form = document.getElementById('submit-form');
  if (form) form.addEventListener('submit', submitProject);

  const interestForm = document.getElementById('interest-form');
  if (interestForm) interestForm.addEventListener('submit', submitInterest);
});

async function submitInterest(e) {
  e.preventDefault();
  const form = document.getElementById('interest-form');
  const btn = form.querySelector('button[type="submit"]');
  const msg = document.getElementById('interest-msg');

  const payload = {
    name: form.int_name.value.trim(),
    age: parseInt(form.int_age.value),
    country: form.int_country.value.trim(),
    email: form.int_email.value.trim() || null,
  };

  btn.disabled = true;
  btn.textContent = 'sending...';

  try {
    const res = await fetch('/api/interest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (res.ok) {
      msg.style.color = '#00c805';
      msg.textContent = "you're on the list. we'll be in touch.";
      form.reset();
    } else {
      msg.style.color = '#c0392b';
      msg.textContent = data.error || 'something went wrong.';
      btn.disabled = false;
      btn.textContent = "i'm interested";
    }
  } catch {
    msg.style.color = '#c0392b';
    msg.textContent = 'network error. try again.';
    btn.disabled = false;
    btn.textContent = "i'm interested";
  }
}
