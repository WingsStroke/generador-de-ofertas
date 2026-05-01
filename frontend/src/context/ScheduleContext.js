import React, { createContext, useContext, useState } from 'react';

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

  const value = {
    scheduleData,
    setScheduleData,
    selectedCell,
    setSelectedCell,
    subjects,
    setSubjects,
  };

  return (
    <ScheduleContext.Provider value={value}>
      {children}
    </ScheduleContext.Provider>
  );
};
