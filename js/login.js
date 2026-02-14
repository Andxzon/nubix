
// Login handling
document.addEventListener('DOMContentLoaded', () => {
    // If already logged in, redirect to index
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

            const username = userInput.value;
            const password = passInput.value;

            if (!username || !password) {
                alert('Por favor ingresa usuario y contraseña');
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
                    body: JSON.stringify({ username, password })
                });

                const data = await response.json();

                if (response.ok) {
                    // Success
                    localStorage.setItem('auth_token', data.token);
                    localStorage.setItem('user', JSON.stringify(data.user));
                    window.location.href = 'index.html';
                } else {
                    // Error
                    alert(data.error || 'Credenciales inválidas');
                    loginBtn.textContent = 'Acceder';
                    loginBtn.disabled = false;
                }
            } catch (error) {
                console.error('Error logging in:', error);
                alert('Error de conexión con el servidor');
                loginBtn.textContent = 'Acceder';
                loginBtn.disabled = false;
            }
        });
    }
});
