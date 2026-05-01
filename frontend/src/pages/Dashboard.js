import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Download, ArrowLeft, FileText } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
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
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
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
            <div className="flex items-center gap-3 text-xs text-slate-500">
              <span>{scheduleData?.programa_nombre || 'Programa'}</span>
              <span>•</span>
              <span>Confianza: {((scheduleData?.nivel_confianza_global || 0) * 100).toFixed(1)}%</span>
            </div>
          </div>
        </div>
        <Button onClick={handleExport} data-testid="export-json-btn">
          <Download className="w-4 h-4 mr-2" />
          Exportar JSON
        </Button>
      </header>

      <div className="flex-1 flex overflow-hidden bg-slate-50">
        {scheduleData && scheduleData.hojas && scheduleData.hojas.length > 1 ? (
          <Tabs defaultValue={scheduleData.hoja_actual || scheduleData.hojas[0]} className="w-full flex flex-col">
            <div className="border-b border-slate-200 px-4 bg-white">
              <TabsList className="h-12">
                {scheduleData.hojas.map((hoja) => (
                  <TabsTrigger
                    key={hoja}
                    value={hoja}
                    className="gap-2"
                    data-testid={`tab-${hoja}`}
                  >
                    <FileText className="w-4 h-4" />
                    {hoja}
                  </TabsTrigger>
                ))}
              </TabsList>
            </div>

            {scheduleData.hojas.map((hoja) => (
              <TabsContent key={hoja} value={hoja} className="flex-1 flex overflow-hidden m-0">
                <div className="flex-1 flex flex-col min-w-0 h-full border-r border-slate-200 bg-white">
                  <div className="h-12 border-b border-slate-200 px-4 flex items-center justify-between bg-slate-50/50">
                    <h2 className="text-sm font-semibold text-slate-700">Horario Editable - {hoja}</h2>
                  </div>
                  <div className="flex-1 overflow-auto p-4">
                    <ScheduleGrid />
                  </div>
                </div>

                <div className="flex-1 flex flex-col min-w-0 h-full bg-white">
                  <div className="h-12 border-b border-slate-200 px-4 flex items-center justify-between bg-slate-50/50">
                    <h2 className="text-sm font-semibold text-slate-700">Vista Original - {hoja}</h2>
                  </div>
                  <div className="flex-1 overflow-auto p-4">
                    <ExcelPreview />
                  </div>
                </div>
              </TabsContent>
            ))}
          </Tabs>
        ) : (
          <>
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
          </>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
