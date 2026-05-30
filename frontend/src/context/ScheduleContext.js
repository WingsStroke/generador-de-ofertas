import React, { createContext, useContext, useState, useCallback } from 'react';

const ScheduleContext = createContext();

export const useSchedule = () => {
  const context = useContext(ScheduleContext);
  if (!context) {
    throw new Error('useSchedule must be used within ScheduleProvider');
  }
  return context;
};

export const ScheduleProvider = ({ children }) => {
  const [scheduleData, setScheduleData] = useState(null);
  const [selectedCell, setSelectedCell] = useState(null);
  const [subjects, setSubjects] = useState([]);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedBlockIds, setSelectedBlockIds] = useState(new Set());
  const [excelHtmlBySheet, setExcelHtmlBySheet] = useState({});
  const [loadingHtmlBySheet, setLoadingHtmlBySheet] = useState({});
  const [zoom, setZoom] = useState(0.75);

  const toggleBlockSelection = useCallback((blockId) => {
    setSelectedBlockIds((prev) => {
      const next = new Set(prev);
      if (next.has(blockId)) {
        next.delete(blockId);
      } else {
        next.add(blockId);
      }
      return next;
    });
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedBlockIds(new Set());
  }, []);

  const exitSelectionMode = useCallback(() => {
    setSelectionMode(false);
    setSelectedBlockIds(new Set());
  }, []);

  const selectAllByMateriaId = useCallback((materiaId) => {
    if (!scheduleData) return;
    const ids = new Set();
    const collections = [];
    if (scheduleData.celdas) collections.push(scheduleData.celdas);
    if (scheduleData.hojas_data) {
      Object.values(scheduleData.hojas_data).forEach((h) => {
        if (h?.celdas) collections.push(h.celdas);
      });
    }
    collections.forEach((cs) =>
      cs.forEach((c) =>
        (c.bloques || []).forEach((b) => {
          if (b.materia_id && b.materia_id === materiaId) ids.add(b.id);
        })
      )
    );
    setSelectedBlockIds(ids);
  }, [scheduleData]);

  const value = {
    scheduleData,
    setScheduleData,
    selectedCell,
    setSelectedCell,
    subjects,
    setSubjects,
    selectionMode,
    setSelectionMode,
    selectedBlockIds,
    toggleBlockSelection,
    clearSelection,
    exitSelectionMode,
    selectAllByMateriaId,
    excelHtmlBySheet,
    setExcelHtmlBySheet,
    loadingHtmlBySheet,
    setLoadingHtmlBySheet,
    zoom,
    setZoom,
  };

  return (
    <ScheduleContext.Provider value={value}>
      {children}
    </ScheduleContext.Provider>
  );
};
