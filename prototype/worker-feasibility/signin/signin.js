import './snapshot.js';
// Setup secret exists only in this closure; never storage, query strings or logs.
const elements = Object.fromEntries([...document.querySelectorAll('[id]')].map(el => [el.id, el]));
let setup = null;
let expiryTimer, snapshotTimer;
if (location.hash) {
  const fragment = new URLSearchParams(location.hash.slice(1));
  const hash = fragment.get('token_hash'), type = fragment.get('type');
  if (/^[A-Za-z0-9_-]{32,256}$/.test(hash || '') && ['signup', 'recovery'].includes(type) && [...fragment.keys()].length === 2) setup = { token_hash: hash, type };
  history.replaceState(null, '', '/');
  if (!setup) elements.message.textContent = 'This setup link is invalid. Request a new private link.';
}
function message(text) { elements.message.textContent = text; }
function signedIn(data) {
  document.title = "Meridian · AXIS";
  setup = null;
  elements.auth.hidden = true;
  elements.workspace.hidden = false;
  elements.form.reset();
  document.body.classList.add("signed-in");
  window.meridianSnapshot.load();
  clearInterval(snapshotTimer);
  snapshotTimer = setInterval(() => window.meridianSnapshot.load(), 60_000);
  clearTimeout(expiryTimer);
  expiryTimer = setTimeout(() => { signedOut(); message("Your session ended. Sign in again."); }, Math.max(0, new Date(data.expires_at).getTime() - Date.now()));
  elements.expiry.textContent = `Session ends at ${new Date(data.expires_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}. Sign in again afterwards.`;
}
function signedOut() {
  document.title = "Meridian · Sign in";
  clearTimeout(expiryTimer);
  clearInterval(snapshotTimer);
  window.meridianSnapshot.clear();
  document.body.classList.remove("signed-in");
  setup = null;
  elements.auth.hidden = false; elements.workspace.hidden = true; elements.form.reset();
  elements.title.textContent = 'Sign in'; elements.intro.textContent = 'Use your approved email address and password.';
  elements.email.hidden = elements['email-label'].hidden = false; elements.email.required = true;
  elements.password.autocomplete = 'current-password'; elements.password.minLength = 1;
  elements['confirm-wrap'].hidden = true; elements.confirm.required = false;
  elements.submit.textContent = 'Sign in'; elements.hint.textContent = 'First visit? Open your private password setup link.';
}
async function request(path, options = {}) {
  return fetch(`/api/v1/session/${path}`, { ...options, credentials: 'same-origin', cache: 'no-store', redirect: 'error', headers: { ...options.headers } });
}
if (setup) {
  elements.title.textContent = 'Choose your password';
  elements.intro.textContent = 'Set a password of at least 12 characters for your approved account.';
  elements.email.hidden = elements['email-label'].hidden = true;
  elements.email.required = false;
  elements.password.autocomplete = 'new-password';
  elements.password.minLength = 12;
  elements['confirm-wrap'].hidden = false;
  elements.confirm.required = true;
  elements.submit.textContent = 'Set password and sign in';
  elements.hint.textContent = 'This private setup link can be used once. Do not share it.';
} else {
  request('current').then(async response => { if (response.ok) signedIn(await response.json()); }).catch(() => message('Unable to check your session. You can try signing in.'));
}
elements.form.addEventListener('submit', async event => {
  event.preventDefault();
  if (setup && elements.password.value !== elements.confirm.value) { message('The passwords do not match.'); return; }
  elements.submit.disabled = true;
  message('Signing in…');
  try {
    const boot = await request('bootstrap');
    if (!boot.ok) throw new Error('unavailable');
    const csrf = (await boot.json()).csrf_token;
    const payload = setup ? { ...setup, password: elements.password.value } : { email: elements.email.value.trim(), password: elements.password.value };
    const response = await request(setup ? 'setup' : 'login', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify(payload) });
    elements.password.value = elements.confirm.value = '';
    if (response.ok) {
      signedIn(await response.json()); message('');
    } else if (response.status === 429) {
      message('Too many sign-in attempts. Wait a minute and try again.');
    } else if (setup) {
      message('Setup did not complete. The link may have expired or been used. Request a new private link if retrying fails.');
    } else if ([401, 403].includes(response.status)) {
      message('Sign-in was not accepted. Check your email and password.');
    } else { message('Sign-in is temporarily unavailable. Try again shortly.'); }
  } catch { message('Unable to connect. Check your connection and try again.'); }
  finally { elements.submit.disabled = false; }
});
elements.logout.addEventListener('click', async () => {
  elements.logout.disabled = true;
  try {
    const match = document.cookie.split(';').map(x => x.trim()).find(x => x.startsWith('__Host-meridian_csrf='));
    const csrf = match ? match.slice(match.indexOf('=') + 1) : '';
    const response = await request('logout', { method: 'POST', headers: { 'X-CSRF-Token': csrf } });
    if (response.ok || response.status === 401) { signedOut(); message('You have signed out.'); }
    else message('Unable to sign out. Try again.');
  } catch { message('Unable to connect. Try signing out again.'); }
  finally { elements.logout.disabled = false; }
});

window.addEventListener("meridian-session-ended", () => { signedOut(); message("Your session ended. Sign in again."); });
window.addEventListener("pagehide", () => { clearInterval(snapshotTimer); window.meridianSnapshot.clear(); });
window.addEventListener("pageshow", event => { if (event.persisted) { signedOut(); request("current").then(async response => { if (response.ok) signedIn(await response.json()); }); } });
