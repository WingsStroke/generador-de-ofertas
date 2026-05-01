import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';

const HistoryContext = createContext();

export const useHistory = () => {
  const context = useContext(HistoryContext);
  if (!context) {
    throw new Error('useHistory must be used within HistoryProvider');
  }
  return context;
};

export const HistoryProvider = ({ children }) => {
  const [history, setHistory] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(-1);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  const pushAction = useCallback((action) => {
    setHistory((prev) => {
      const newHistory = prev.slice(0, currentIndex + 1);
      newHistory.push(action);
      return newHistory.slice(-50);
    });
    setCurrentIndex((prev) => Math.min(prev + 1, 49));
    setHasUnsavedChanges(true);
  }, [currentIndex]);

  const undo = useCallback(() => {
    if (currentIndex >= 0) {
      const action = history[currentIndex];
      setCurrentIndex((prev) => prev - 1);
      return action;
    }
    return null;
  }, [currentIndex, history]);

  const redo = useCallback(() => {
    if (currentIndex < history.length - 1) {
      setCurrentIndex((prev) => prev + 1);
      const action = history[currentIndex + 1];
      return action;
    }
    return null;
  }, [currentIndex, history]);

  const canUndo = currentIndex >= 0;
  const canRedo = currentIndex < history.length - 1;

  const clearHistory = useCallback(() => {
    setHistory([]);
    setCurrentIndex(-1);
    setHasUnsavedChanges(false);
  }, []);

  const markAsSaved = useCallback(() => {
    setHasUnsavedChanges(false);
  }, []);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        if (canUndo) {
          const action = undo();
          if (action && action.onUndo) {
            action.onUndo();
          }
        }
      }
      
      if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
        e.preventDefault();
        if (canRedo) {
          const action = redo();
          if (action && action.onRedo) {
            action.onRedo();
          }
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [canUndo, canRedo, undo, redo]);

  const value = {
    pushAction,
    undo,
    redo,
    canUndo,
    canRedo,
    hasUnsavedChanges,
    clearHistory,
    markAsSaved,
    historyLength: history.length,
    currentIndex,
  };

  return <HistoryContext.Provider value={value}>{children}</HistoryContext.Provider>;
};
