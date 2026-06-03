import React, { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

const AuthContext = createContext(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [token, setToken] = useState(() => localStorage.getItem('token'));
  const [username, setUsername] = useState(() => localStorage.getItem('username'));
  const [role, setRole] = useState(() => localStorage.getItem('role') || 'user');
  const [isAuthenticated, setIsAuthenticated] = useState(!!localStorage.getItem('token'));

  useEffect(() => {
    // Proactively check if the token is already expired
    if (token) {
      try {
        const payload = JSON.parse(atob(token.split('.')[1]));
        if (payload.exp * 1000 < Date.now()) {
          logout();
          toast.error("Sesión expirada. Por favor, inicia sesión nuevamente.");
          return;
        }
      } catch (e) {
        // Ignore parsing errors
      }
    }

    // Check every minute
    const interval = setInterval(() => {
      if (token) {
        try {
          const payload = JSON.parse(atob(token.split('.')[1]));
          if (payload.exp * 1000 < Date.now()) {
            logout();
            toast.error("Sesión expirada. Por favor, inicia sesión nuevamente.");
          }
        } catch (e) {}
      }
    }, 60000);

    // Interceptor para inyectar el token en todas las peticiones
    const requestInterceptor = axios.interceptors.request.use(
      (config) => {
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Interceptor para detectar cuando un token expiró (401)
    const responseInterceptor = axios.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response && error.response.status === 401) {
          logout();
          toast.error("Sesión expirada. Por favor, inicia sesión nuevamente.");
        }
        return Promise.reject(error);
      }
    );

    return () => {
      clearInterval(interval);
      axios.interceptors.request.eject(requestInterceptor);
      axios.interceptors.response.eject(responseInterceptor);
    };
  }, [token]);

  const login = (newToken, newUsername, newRole = 'user') => {
    setToken(newToken);
    setUsername(newUsername);
    setRole(newRole);
    setIsAuthenticated(true);
    localStorage.setItem('token', newToken);
    localStorage.setItem('username', newUsername);
    localStorage.setItem('role', newRole);
  };

  const logout = () => {
    setToken(null);
    setUsername(null);
    setRole('user');
    setIsAuthenticated(false);
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    localStorage.removeItem('role');
    window.location.href = '/login';
  };

  return (
    <AuthContext.Provider value={{ token, username, role, isAuthenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};
