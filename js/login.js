
// Login handling con Cloudflare Turnstile
document.addEventListener('DOMContentLoaded', () => {
    // Si ya está autenticado, redirigir al index
    if (localStorage.getItem('auth_token')) {
        window.location.href = 'index.html';
        return;
    }

    const loginForm = document.querySelector('.login-form');
    const loginBtn = document.querySelector('.login-btn');
    const userInput = document.querySelector('input[type="text"]');
    const passInput = document.querySelector('input[type="password"]');

    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const username = userInput.value.trim();
            const password = passInput.value;

            if (!username || !password) {
                alert('Por favor ingresa usuario y contraseña');
                return;
            }

            // Obtener el token generado por Cloudflare Turnstile
            // El widget lo guarda en un input hidden llamado "cf-turnstile-response"
            const turnstileToken = document.querySelector('[name="cf-turnstile-response"]')?.value;

            if (!turnstileToken) {
                alert('Por favor completa la verificación de seguridad (Turnstile)');
                return;
            }

            loginBtn.textContent = 'Verificando...';
            loginBtn.disabled = true;

            try {
                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        username,
                        password,
                        turnstile_token: turnstileToken  // ← enviamos el token al backend
                    })
                });

                const data = await response.json();

                if (response.ok) {
                    // Éxito
                    localStorage.setItem('auth_token', data.token);
                    localStorage.setItem('user', JSON.stringify(data.user));
                    window.location.href = 'index.html';
                } else {
                    // Error
                    alert(data.error || 'Credenciales inválidas');
                    loginBtn.textContent = 'Acceder';
                    loginBtn.disabled = false;
                    // Resetear el widget Turnstile para que el usuario pueda intentar de nuevo
                    if (window.turnstile) {
                        window.turnstile.reset('#cf-turnstile-widget');
                    }
                }
            } catch (error) {
                console.error('Error logging in:', error);
                alert('Error de conexión con el servidor');
                loginBtn.textContent = 'Acceder';
                loginBtn.disabled = false;
                if (window.turnstile) {
                    window.turnstile.reset('#cf-turnstile-widget');
                }
            }
        });
    }
});
