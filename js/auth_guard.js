
// Immediately check for auth token
(function () {
    const token = localStorage.getItem('auth_token');
    if (!token) {
        // Current path
        const path = window.location.pathname;
        // Don't redirect if we are already on login page
        if (!path.endsWith('login.html')) {
            window.location.href = 'login.html';
        }
    }
})();

// Function to handle logout
function logout() {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user');
    window.location.href = 'login.html';
}
