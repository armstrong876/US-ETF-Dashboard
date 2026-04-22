/**
 * auth.js | Authentication & Authorization for Armstrong Capital Dashboard
 */

(function() {
    'use strict';

    const AUTH_KEY = 'armstrong_auth_session';

    const USERS = {
        'admin': { pass: 'armstrong123', role: 'editor', name: 'Administrator' },
        'team':  { pass: 'viewer123',    role: 'viewer', name: 'Team Member' }
    };

    window.Auth = {
        login: function(userId, password) {
            const user = USERS[userId.toLowerCase()];
            if (user && user.pass === password) {
                const session = {
                    userId: userId,
                    role: user.role,
                    name: user.name,
                    timestamp: Date.now()
                };
                localStorage.setItem(AUTH_KEY, JSON.stringify(session));
                return { success: true, role: user.role };
            }
            return { success: false, message: 'Invalid User ID or Password' };
        },

        logout: function() {
            localStorage.removeItem(AUTH_KEY);
            window.location.href = 'login.html';
        },

        getSession: function() {
            const sessionData = localStorage.getItem(AUTH_KEY);
            if (!sessionData) return null;
            return JSON.parse(sessionData);
        },

        isLoggedIn: function() {
            return this.getSession() !== null;
        },

        checkAccess: function() {
            if (!this.isLoggedIn() && !window.location.pathname.includes('login.html')) {
                window.location.href = 'login.html';
            }
        },

        isEditor: function() {
            const sess = this.getSession();
            return sess && sess.role === 'editor';
        }
    };

    // Auto-check on script load
    Auth.checkAccess();

})();
