
// ============================================================
//  MeteoIoT — Login con Cloudflare Turnstile + Cookie Session
// ============================================================

// ── Callbacks globales de Turnstile (deben estar en window scope) ────────────

window.onTurnstileVerified = function (token) {
    // Cloudflare aprobó al usuario → habilitar botón
    const btn = document.getElementById('login-submit-btn');
    if (btn) {
        btn.disabled = false;
        btn.classList.add('turnstile-ok');
    }
};

window.onTurnstileExpired = function () {
    // El token caducó (tokens duran ~5 min) → volver a bloquear
    const btn = document.getElementById('login-submit-btn');
    if (btn) {
        btn.disabled = true;
        btn.classList.remove('turnstile-ok');
    }
};

window.onTurnstileError = function () {
    // Error en el widget (sin red, etc.) → bloquear
    const btn = document.getElementById('login-submit-btn');
    if (btn) {
        btn.disabled = true;
        btn.classList.remove('turnstile-ok');
    }
};

// ── Lógica del formulario ─────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {

    // Verificar sesión existente vía API (no localStorage)
    fetch('/api/me', { credentials: 'include' })
        .then(res => { if (res.ok) window.location.href = 'index.html'; })
        .catch(() => { /* no hay sesión activa, mostramos login */ });

    const loginForm  = document.querySelector('.login-form');
    const loginBtn   = document.getElementById('login-submit-btn');
    const userInput  = document.querySelector('input[type="text"]');
    const passInput  = document.querySelector('input[type="password"]');

    if (!loginForm) return;

    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const username = userInput.value.trim();
        const password = passInput.value;

        if (!username || !password) {
            showError('Por favor ingresa usuario y contraseña');
            return;
        }

        // Obtener token del input hidden que inyecta el widget de Turnstile
        const turnstileToken = document.querySelector('[name="cf-turnstile-response"]')?.value;

        if (!turnstileToken) {
            showError('Por favor completa la verificación de seguridad');
            return;
        }

        setLoading(true);

        try {
            const response = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',          // ← necesario para recibir la cookie
                body: JSON.stringify({ username, password, turnstile_token: turnstileToken })
            });

            const data = await response.json();

            if (response.ok) {
                // ✅ La sesión se guarda en cookie HttpOnly (el backend la setea)
                // No guardamos nada en localStorage
                window.location.href = 'index.html';
            } else {
                showError(data.error || 'Credenciales inválidas');
                setLoading(false);
                resetTurnstile();
            }
        } catch (err) {
            console.error('Error de conexión:', err);
            showError('Error de conexión con el servidor');
            setLoading(false);
            resetTurnstile();
        }
    });

    // ── Helpers ───────────────────────────────────────────────────────────────

    function setLoading(on) {
        loginBtn.textContent = on ? 'Verificando...' : 'Acceder';
        loginBtn.disabled    = on;
    }

    function showError(msg) {
        // Eliminar error previo si existe
        document.querySelector('.login-error-msg')?.remove();

        const p = document.createElement('p');
        p.className   = 'login-error-msg';
        p.textContent = msg;
        p.style.cssText = 'color:#ff6b6b;font-size:.85rem;text-align:center;margin:.5rem 0 0;';
        loginBtn.insertAdjacentElement('afterend', p);

        // Auto-eliminar a los 5 segundos
        setTimeout(() => p.remove(), 5000);
    }

    function resetTurnstile() {
        if (window.turnstile) {
            window.turnstile.reset('#cf-turnstile-widget');
            // Al resetear, el botón vuelve a quedar deshabilitado hasta nueva verificación
            loginBtn.disabled = true;
            loginBtn.classList.remove('turnstile-ok');
        }
    }
});
