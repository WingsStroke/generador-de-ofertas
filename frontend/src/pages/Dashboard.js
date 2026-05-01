import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Download, ArrowLeft } from 'lucide-react';
import { Button } from '../components/ui/button';
import { toast } from 'sonner';
import { useSchedule } from '../context/ScheduleContext';
import ScheduleGrid from '../components/ScheduleGrid';
import ExcelPreview from '../components/ExcelPreview';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const Dashboard = () => {
  const { scheduleId } = useParams();
  const { scheduleData, setScheduleData, setSubjects } = useSchedule();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [scheduleRes, subjectsRes] = await Promise.all([
          axios.get(`${API}/schedule/${scheduleId}`),
          axios.get(`${API}/subjects`),
        ]);

        setScheduleData(scheduleRes.data);
        setSubjects(subjectsRes.data);
      } catch (error) {
        console.error('Error fetching data:', error);
        toast.error('Error al cargar el horario');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [scheduleId, setScheduleData, setSubjects]);

  const handleExport = async () => {
    try {
      const response = await axios.post(`${API}/schedule/${scheduleId}/export`);
      const blob = new Blob([JSON.stringify(response.data, null, 2)], {
        type: 'application/json',
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `horario_${scheduleId}.json`;
      a.click();
      toast.success('Horario exportado exitosamente');
    } catch (error) {
      console.error('Error exporting schedule:', error);
      toast.error('Error al exportar el horario');
    }
  };

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-slate-600">Cargando horario...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col">
      <header className="h-16 border-b border-slate-200 px-6 flex items-center justify-between bg-white z-50 sticky top-0">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => window.history.back()} data-testid="back-btn">
            <ArrowLeft className="w-4 h-4 mr-2" />
            Volver
          </Button>
          <div>
            <h1 className="text-xl font-semibold text-slate-900">
              {scheduleData?.nombre_archivo || 'Horario'}
            </h1>
            <p className="text-xs text-slate-500">
              Confianza: {((scheduleData?.nivel_confianza_global || 0) * 100).toFixed(1)}%
            </p>
          </div>
        </div>
        <Button onClick={handleExport} data-testid="export-json-btn">
          <Download className="w-4 h-4 mr-2" />
          Exportar JSON
        </Button>
      </header>

      <div className="flex-1 flex overflow-hidden bg-slate-50">
        <div className="flex-1 flex flex-col min-w-0 h-full border-r border-slate-200 bg-white">
          <div className="h-12 border-b border-slate-200 px-4 flex items-center justify-between bg-slate-50/50">
            <h2 className="text-sm font-semibold text-slate-700">Horario Editable</h2>
          </div>
          <div className="flex-1 overflow-auto p-4">
            <ScheduleGrid />
          </div>
        </div>

        <div className="flex-1 flex flex-col min-w-0 h-full bg-white">
          <div className="h-12 border-b border-slate-200 px-4 flex items-center justify-between bg-slate-50/50">
            <h2 className="text-sm font-semibold text-slate-700">Vista Original</h2>
          </div>
          <div className="flex-1 overflow-auto p-4">
            <ExcelPreview />
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
