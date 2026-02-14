
// Admin Panel visibility logic
document.addEventListener('DOMContentLoaded', () => {
    const userStr = localStorage.getItem('user');
    const adminBtn = document.getElementById('admin-btn');

    if (userStr) {
        try {
            const user = JSON.parse(userStr);
            if (user.username === 'admin') {
                if (adminBtn) adminBtn.style.display = 'flex';
                const reportBtn = document.getElementById('generate-new-report-btn');
                if (reportBtn) reportBtn.style.display = 'flex';
            }
        } catch (e) {
            console.error('Error parsing user data:', e);
        }
    }
});
