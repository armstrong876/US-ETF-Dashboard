/**
 * auth.js | v1.0.1 | Authentication & Authorization for Armstrong Capital Dashboard
 */

(function() {
    'use strict';

    const AUTH_KEY = 'armstrong_auth_session';
    const SESSION_TIMEOUT = 30 * 60 * 1000; // 30 minutes in milliseconds

    const USERS = {
        'armstrongetf': { pass: 'Aetf@1500', role: 'editor', name: 'Armstrong Capital' }
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
            const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
            let sessionData = localStorage.getItem(AUTH_KEY);
            if (!sessionData && isLocal) {
                const mockSession = {
                    userId: 'armstrongetf',
                    role: 'editor',
                    name: 'Armstrong Capital (Local)',
                    timestamp: Date.now()
                };
                localStorage.setItem(AUTH_KEY, JSON.stringify(mockSession));
                sessionData = localStorage.getItem(AUTH_KEY);
            }
            if (!sessionData) return null;
            
            const session = JSON.parse(sessionData);
            const now = Date.now();
            
            // Check if session has expired (30 minutes)
            if (now - session.timestamp > SESSION_TIMEOUT) {
                if (isLocal) {
                    // Update timestamp on localhost instead of logging out
                    session.timestamp = now;
                    localStorage.setItem(AUTH_KEY, JSON.stringify(session));
                    return session;
                }
                console.log("Session expired. Logging out...");
                this.logout();
                return null;
            }
            
            return session;
        },

        isLoggedIn: function() {
            return this.getSession() !== null;
        },

        checkAccess: function() {
            const isLoginPage = window.location.pathname.includes('login.html');
            const session = this.getSession();

            if (!session && !isLoginPage) {
                window.location.href = 'login.html';
            } else if (session && isLoginPage) {
                // If already logged in and on login page, go to dashboard
                window.location.href = '/';
            }
        },

        isEditor: function() {
            const sess = this.getSession();
            return sess && sess.role === 'editor';
        }
    };

    // Auto-check on script load
    Auth.checkAccess();

    // Check expiration every minute while on the page
    setInterval(() => {
        Auth.getSession();
    }, 60000);

})();
