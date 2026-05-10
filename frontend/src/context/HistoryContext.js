import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';

const HistoryContext = createContext();

export const useHistory = () => {
  const context = useContext(HistoryContext);
  if (!context) {
    throw new Error('useHistory must be used within HistoryProvider');
  }
  return context;
};

export const HistoryProvider = ({ children }) => {
  // Usar ref para el historial para evitar stale closures
  const historyRef = useRef([]);
  const indexRef = useRef(-1);

  // Estado solo para forzar re-render y exponer canUndo/canRedo
  const [snapshot, setSnapshot] = useState({ length: 0, index: -1 });
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  const syncSnapshot = useCallback(() => {
    setSnapshot({ length: historyRef.current.length, index: indexRef.current });
  }, []);

  const pushAction = useCallback((action) => {
    // Descartar el futuro si estamos en medio del historial
    historyRef.current = historyRef.current.slice(0, indexRef.current + 1);
    historyRef.current.push(action);
    // Limitar a 50 entradas
    if (historyRef.current.length > 50) {
      historyRef.current = historyRef.current.slice(-50);
    }
    indexRef.current = historyRef.current.length - 1;
    setHasUnsavedChanges(true);
    syncSnapshot();
  }, [syncSnapshot]);

  // performUndo ejecuta el callback onUndo directamente
  const performUndo = useCallback(() => {
    if (indexRef.current < 0) return;
    const action = historyRef.current[indexRef.current];
    indexRef.current -= 1;
    syncSnapshot();
    if (action && action.onUndo) {
      action.onUndo();
    }
  }, [syncSnapshot]);

  // performRedo ejecuta el callback onRedo directamente
  const performRedo = useCallback(() => {
    if (indexRef.current >= historyRef.current.length - 1) return;
    indexRef.current += 1;
    const action = historyRef.current[indexRef.current];
    syncSnapshot();
    if (action && action.onRedo) {
      action.onRedo();
    }
  }, [syncSnapshot]);

  const canUndo = snapshot.index >= 0;
  const canRedo = snapshot.index < snapshot.length - 1;

  const clearHistory = useCallback(() => {
    historyRef.current = [];
    indexRef.current = -1;
    setHasUnsavedChanges(false);
    syncSnapshot();
  }, [syncSnapshot]);

  const markAsSaved = useCallback(() => {
    setHasUnsavedChanges(false);
  }, []);

  // Atajos de teclado
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        performUndo();
      }
      if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
        e.preventDefault();
        performRedo();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [performUndo, performRedo]);

  const value = {
    pushAction,
    undo: performUndo,
    redo: performRedo,
    canUndo,
    canRedo,
    hasUnsavedChanges,
    clearHistory,
    markAsSaved,
    historyLength: snapshot.length,
    currentIndex: snapshot.index,
  };

  return <HistoryContext.Provider value={value}>{children}</HistoryContext.Provider>;
};
