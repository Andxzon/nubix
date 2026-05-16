
// Admin Panel visibility — usa datos del usuario desde auth_guard.js
function checkAdminAccess(user) {
    const adminBtn  = document.getElementById('admin-btn');
    const reportBtn = document.getElementById('generate-new-report-btn');

    if (user && user.username === 'admin') {
        if (adminBtn)  adminBtn.style.display  = 'flex';
        if (reportBtn) reportBtn.style.display = 'flex';
    }
}

// 1. Escuchar si el usuario se carga después de que este script esté listo
document.addEventListener('userLoaded', (e) => {
    checkAdminAccess(e.detail);
});

// 2. Por si acaso auth_guard ya terminó antes de que este script cargara
document.addEventListener('DOMContentLoaded', () => {
    if (window.__currentUser) {
        checkAdminAccess(window.__currentUser);
    }
});
