import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ScheduleProvider } from './context/ScheduleContext';
import { HistoryProvider } from './context/HistoryContext';
import { Toaster } from './components/ui/sonner';
import Upload from './pages/Upload';
import Dashboard from './pages/Dashboard';
import Teachers from './pages/Teachers';
import Login from './pages/Login';
import { AuthProvider } from './context/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import '@/App.css';

function App() {
  return (
    <ScheduleProvider>
      <HistoryProvider>
        <div className="App">
          <BrowserRouter>
            <AuthProvider>
              <Routes>
                <Route path="/login" element={<Login />} />
                <Route path="/" element={<ProtectedRoute><Upload /></ProtectedRoute>} />
                <Route path="/dashboard/:scheduleId" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
                <Route path="/teachers" element={<ProtectedRoute><Teachers /></ProtectedRoute>} />
              </Routes>
            </AuthProvider>
          </BrowserRouter>
          <Toaster position="bottom-right" />
        </div>
      </HistoryProvider>
    </ScheduleProvider>
  );
}

export default App;
