import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { toast } from 'sonner';
import { useAuth } from './AuthContext';

const CollabContext = createContext(null);

export const useCollab = () => {
  const context = useContext(CollabContext);
  if (!context) {
    throw new Error('useCollab must be used within a CollabProvider');
  }
  return context;
};

export const CollabProvider = ({ scheduleId, children }) => {
  const { username, token, logout } = useAuth();

  const [isConnected, setIsConnected] = useState(false);
  const [presence, setPresence] = useState([]);
  const [locks, setLocks] = useState({}); // { "Sheet 1": "Auditor-1234" }
  const [remoteUpdates, setRemoteUpdates] = useState([]);
  
  const wsRef = useRef(null);
  const pingIntervalRef = useRef(null);

  useEffect(() => {
    if (!scheduleId) return;

    const backendUrl = process.env.REACT_APP_BACKEND_URL || window.location.origin;
    const wsUrl = backendUrl.replace(/^http/, 'ws') + `/api/ws/collab/${scheduleId}?token=${token}`;

    const connectWs = () => {
      wsRef.current = new WebSocket(wsUrl);

      wsRef.current.onopen = () => {
        setIsConnected(true);
        pingIntervalRef.current = setInterval(() => {
          if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ action: 'ping' }));
          }
        }, 30000);
      };

      wsRef.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          switch (data.action) {
            case 'INIT_STATE':
              setPresence(data.presence);
              setLocks(data.locks);
              break;
            case 'PRESENCE_UPDATE':
              setPresence(data.presence);
              break;
            case 'LOCK_STATUS_UPDATE':
              setLocks(data.locks);
              break;
            case 'LOCK_GRANTED':
              // Opcional: mostrar un indicador sutil
              break;
            case 'LOCK_DENIED':
              toast.error(`No puedes editar ${data.sheet}: ${data.reason}`);
              break;
            case 'error':
              toast.error(data.message);
              break;
            case 'pong':
              // Heartbeat ok
              break;
            case 'DATA_CHANGED':
              // We expose this so Dashboard can auto-refresh
              setRemoteUpdates(prev => [...prev, { sheet: data.sheet, byUser: data.by_user, timestamp: Date.now() }]);
              break;
            case 'FORCE_UNLOCKED':
              if (data.victim === username) {
                toast.warning(`Tu sesión en la hoja ${data.sheet} fue desbloqueada por el administrador ${data.by}`, {
                  duration: 5000,
                });
              }
              break;
            default:
              break;
          }
        } catch (e) {
          console.error("Error parsing WS message", e);
        }
      };

      wsRef.current.onclose = (event) => {
        setIsConnected(false);
        if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
        
        if (event.code === 4003) {
          toast.error("Sesión expirada. Por favor, inicia sesión nuevamente.");
          logout();
          return;
        }
        
        // Intentar reconectar después de 5 segundos
        setTimeout(() => {
          if (scheduleId) connectWs();
        }, 5000);
      };
      
      wsRef.current.onerror = (err) => {
        console.error("WebSocket error:", err);
      };
    };

    connectWs();

    return () => {
      if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [scheduleId, username, token]);

  const requestLock = useCallback((sheet) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'REQUEST_LOCK', sheet }));
    }
  }, []);

  const releaseLock = useCallback((sheet) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'RELEASE_LOCK', sheet }));
    }
  }, []);

  const forceUnlock = useCallback((sheet) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'FORCE_UNLOCK', sheet }));
    }
  }, []);

  const notifyUpdate = useCallback((sheet) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'NOTIFY_UPDATE', sheet }));
    }
  }, []);

  const isSheetLockedByOther = useCallback((sheet) => {
    const owner = locks[sheet];
    return owner && owner !== username;
  }, [locks, username]);

  return (
    <CollabContext.Provider value={{
      username,
      isConnected,
      presence,
      locks,
      remoteUpdates,
      requestLock,
      releaseLock,
      forceUnlock,
      notifyUpdate,
      isSheetLockedByOther
    }}>
      {children}
    </CollabContext.Provider>
  );
};
