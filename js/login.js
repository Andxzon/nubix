
// ============================================================
//  MeteoIoT — Login con 2FA e integración Turnstile
// ============================================================

let currentTurnstileToken = null;
let pendingUserId = null;

// --- Callbacks de Cloudflare Turnstile ---
window.onTurnstileVerified = function(token) {
    currentTurnstileToken = token;
    const btn = document.getElementById('login-submit-btn');
    btn.disabled = false;
    btn.classList.add('turnstile-ok');
};

window.onTurnstileExpired = function() {
    currentTurnstileToken = null;
    const btn = document.getElementById('login-submit-btn');
    btn.disabled = true;
    btn.classList.remove('turnstile-ok');
};

window.onTurnstileError = function() {
    currentTurnstileToken = null;
    const btn = document.getElementById('login-submit-btn');
    btn.disabled = true;
    btn.classList.remove('turnstile-ok');
};

document.addEventListener('DOMContentLoaded', () => {
    const loginForm = document.querySelector('.login-form');
    const credsSection = document.getElementById('credentials-section');
    const tfaSection = document.getElementById('2fa-section');
    const verify2faBtn = document.getElementById('verify-2fa-btn');

    // Al cargar la página, verificar si ya está autenticado
    fetch('/api/me', { credentials: 'include' })
        .then(res => { if (res.ok) window.location.href = 'index.html'; });

    // PASO 1: Enviar Usuario y Contraseña + Turnstile
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;
        const submitBtn = document.getElementById('login-submit-btn');

        if (!currentTurnstileToken) {
            alert('Por favor, completa la verificación de seguridad.');
            return;
        }

        submitBtn.disabled = true;
        submitBtn.textContent = 'Verificando...';

        try {
            const response = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    username, 
                    password, 
                    turnstile_token: currentTurnstileToken 
                })
            });

            const data = await response.json();

            if (response.ok && data.requires_2fa) {
                // Éxito parcial: ocultar login y mostrar campo 2FA
                pendingUserId = data.user_id;
                document.getElementById('masked-email').textContent = data.email_masked;
                
                credsSection.style.display = 'none';
                tfaSection.style.display = 'block';
                document.querySelector('.login-title').textContent = 'Paso de Seguridad';
            } else if (!response.ok) {
                alert(data.error || 'Error en el inicio de sesión');
                // Resetear Turnstile en caso de error para que el usuario pueda reintentar
                if (typeof turnstile !== 'undefined') turnstile.reset();
                submitBtn.textContent = 'Acceder';
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Error de conexión con el servidor.');
            submitBtn.disabled = false;
            submitBtn.textContent = 'Acceder';
        }
    });

    // PASO 2: Verificar código 2FA
    verify2faBtn.addEventListener('click', async () => {
        const code = document.getElementById('2fa-code').value.trim();

        if (code.length < 6) {
            alert('El código debe tener 6 dígitos.');
            return;
        }

        verify2faBtn.disabled = true;
        verify2faBtn.textContent = 'Comprobando...';

        try {
            const response = await fetch('/api/verify-2fa', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    user_id: pendingUserId, 
                    code: code 
                })
            });

            const data = await response.json();

            if (response.ok) {
                // Éxito completo: redirigir
                window.location.href = 'index.html';
            } else {
                alert(data.error || 'Código incorrecto');
                verify2faBtn.disabled = false;
                verify2faBtn.textContent = 'Verificar Código';
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Error al verificar el código.');
            verify2faBtn.disabled = false;
            verify2faBtn.textContent = 'Verificar Código';
        }
    });
});
