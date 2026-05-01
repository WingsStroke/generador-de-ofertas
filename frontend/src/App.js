import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ScheduleProvider } from './context/ScheduleContext';
import { Toaster } from './components/ui/sonner';
import Upload from './pages/Upload';
import Dashboard from './pages/Dashboard';
import '@/App.css';

function App() {
  return (
    <ScheduleProvider>
      <div className="App">
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Upload />} />
            <Route path="/dashboard/:scheduleId" element={<Dashboard />} />
          </Routes>
        </BrowserRouter>
        <Toaster position="top-right" />
      </div>
    </ScheduleProvider>
  );
}

export default App;
