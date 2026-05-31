import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ScheduleProvider } from './context/ScheduleContext';
import { HistoryProvider } from './context/HistoryContext';
import { Toaster } from './components/ui/sonner';
import Upload from './pages/Upload';
import Dashboard from './pages/Dashboard';
import Teachers from './pages/Teachers';
import '@/App.css';

function App() {
  return (
    <ScheduleProvider>
      <HistoryProvider>
        <div className="App">
          <BrowserRouter>
            <Routes>
              <Route path="/" element={<Upload />} />
              <Route path="/dashboard/:scheduleId" element={<Dashboard />} />
              <Route path="/teachers" element={<Teachers />} />
            </Routes>
          </BrowserRouter>
          <Toaster position="bottom-right" />
        </div>
      </HistoryProvider>
    </ScheduleProvider>
  );
}

export default App;
