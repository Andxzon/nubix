
// ============================================================
//  MeteoIoT — Auth Guard (verifica sesión por cookie HttpOnly)
// ============================================================
//  La sesión ya NO se guarda en localStorage.
//  El backend envía una cookie HttpOnly; este guard la verifica
//  llamando a /api/me. Si no hay sesión, redirige al login.
// ============================================================

(function () {
    const path = window.location.pathname;
    if (path.endsWith('login.html')) return; // ya estamos en login, no redirigir

    fetch('/api/me', { credentials: 'include' })
        .then(res => {
            if (!res.ok) {
                window.location.href = 'login.html';
            } else {
                // Guardar datos del usuario en memoria para que admin.js los use
                res.json().then(data => {
                    window.__currentUser = data.user || null;
                    // Disparar evento para que otros scripts reaccionen
                    document.dispatchEvent(new CustomEvent('userLoaded', { detail: data.user }));
                });
            }
        })
        .catch(() => {
            window.location.href = 'login.html';
        });
})();

// Función global de cierre de sesión
function logout() {
    fetch('/api/logout', {
        method: 'POST',
        credentials: 'include'
    }).finally(() => {
        window.__currentUser = null;
        window.location.href = 'login.html';
    });
}
