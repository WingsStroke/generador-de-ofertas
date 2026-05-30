import React, { useEffect, useState, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Download, ArrowLeft, FileText, Undo2, Redo2, MousePointer2, BookOpenCheck } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { Badge } from '../components/ui/badge';
import { toast } from 'sonner';
import { useSchedule } from '../context/ScheduleContext';
import { useHistory } from '../context/HistoryContext';
import ScheduleGrid from '../components/ScheduleGrid';
import ExcelPreview from '../components/ExcelPreview';
import GlobalSearch from '../components/GlobalSearch';
import DictionaryPanel from '../components/DictionaryPanel';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const Dashboard = () => {
  const { scheduleId } = useParams();
  const { scheduleData, setScheduleData, setSubjects, selectionMode, setSelectionMode,
    selectedBlockIds, exitSelectionMode, setExcelHtmlBySheet, excelHtmlBySheet, setLoadingHtmlBySheet } = useSchedule();
  const { canUndo, canRedo, hasUnsavedChanges, undo, redo } = useHistory();
  const [loading, setLoading] = useState(true);
  const [currentSheet, setCurrentSheet] = useState(null);
  const [showDictionary, setShowDictionary] = useState(false);

  const loadSheetHtml = useCallback(async (sheetName) => {
    if (!scheduleId || !sheetName) return;
    try {
      setLoadingHtmlBySheet((prev) => ({ ...prev, [sheetName]: true }));
      const encodedSheet = encodeURIComponent(sheetName);
      const res = await axios.get(`${API}/schedule/${scheduleId}/sheet-preview/${encodedSheet}`, {
        responseType: 'text',
      });
      setExcelHtmlBySheet((prev) => ({ ...prev, [sheetName]: res.data }));
    } catch (err) {
      // El archivo puede no estar disponible si el servidor fue reiniciado.
      // En ese caso, ExcelPreview cae al fallback de reconstrucción simple.
      console.warn(`Vista HTML no disponible para hoja "${sheetName}":`, err?.response?.status);
    } finally {
      setLoadingHtmlBySheet((prev) => ({ ...prev, [sheetName]: false }));
    }
  }, [scheduleId, setExcelHtmlBySheet, setLoadingHtmlBySheet]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [scheduleRes, subjectsRes] = await Promise.all([
          axios.get(`${API}/schedule/${scheduleId}`),
          axios.get(`${API}/subjects`),
        ]);

        setScheduleData(scheduleRes.data);
        const firstSheet = scheduleRes.data.hoja_actual || (scheduleRes.data.hojas && scheduleRes.data.hojas[0]);
        setCurrentSheet(firstSheet);
        setSubjects(subjectsRes.data);

        // Pre-marcar TODAS las hojas como "cargando" antes de que ExcelPreview
        // pueda renderizar, así nunca muestra el fallback sin estilo.
        const allSheets = scheduleRes.data.hojas || [];
        if (allSheets.length > 0) {
          const loadingMap = {};
          allSheets.forEach((h) => { loadingMap[h] = true; });
          setLoadingHtmlBySheet(loadingMap);
        }

        // Cargar HTML de la primera hoja inmediatamente
        if (firstSheet) {
          loadSheetHtml(firstSheet);
        }
        // Pre-cargar las demás hojas en segundo plano con escalonado mínimo
        allSheets.forEach((hoja, idx) => {
          if (hoja !== firstSheet) {
            setTimeout(() => loadSheetHtml(hoja), 200 * idx);
          }
        });
      } catch (error) {
        console.error('Error fetching data:', error);
        toast.error('Error al cargar el horario');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [scheduleId, setScheduleData, setSubjects, loadSheetHtml]);

  const loadSheetData = (sheetName) => {
    if (!scheduleData || !scheduleData.hojas_data) return;
    
    const sheetData = scheduleData.hojas_data[sheetName];
    if (sheetData) {
      // Pre-marcar como cargando ANTES de setScheduleData para evitar
      // el flash del fallback sin estilo mientras se descarga el HTML.
      if (!excelHtmlBySheet?.[sheetName]) {
        setLoadingHtmlBySheet((prev) => ({ ...prev, [sheetName]: true }));
      }
      const updatedSchedule = {
        ...scheduleData,
        hoja_actual: sheetName,
        celdas: sheetData.celdas || [],
        estructura_dias: sheetData.estructura_dias || [],
        estructura_horas: sheetData.estructura_horas || [],
        excel_preview: sheetData.excel_preview || [],
      };
      setScheduleData(updatedSchedule);
      setCurrentSheet(sheetName);
      // Cargar HTML de la hoja si aún no está cargado
      loadSheetHtml(sheetName);
    }
  };

  const handleNavigateFromSearch = (hoja, dia, hora_inicio) => {
    loadSheetData(hoja);
    setTimeout(() => {
      const cell = document.querySelector(`[data-testid="schedule-cell-${dia}-${hora_inicio}"]`);
      if (cell) {
        cell.scrollIntoView({ behavior: 'smooth', block: 'center' });
        cell.classList.add('ring-2', 'ring-blue-500', 'ring-offset-2');
        setTimeout(() => {
          cell.classList.remove('ring-2', 'ring-blue-500', 'ring-offset-2');
        }, 2000);
      }
    }, 300);
  };

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
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-semibold text-slate-900">
                {scheduleData?.nombre_archivo || 'Horario'}
              </h1>
              {hasUnsavedChanges && (
                <Badge variant="outline" className="text-amber-600 border-amber-600">
                  Sin guardar
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-3 text-xs text-slate-500">
              <span>{scheduleData?.programa_nombre || 'Programa'}</span>
              <span>•</span>
              <span>Confianza: {((scheduleData?.nivel_confianza_global || 0) * 100).toFixed(1)}%</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <GlobalSearch onNavigate={handleNavigateFromSearch} />
          <Button
            variant={selectionMode ? 'default' : 'outline'}
            size="sm"
            onClick={() => {
              if (selectionMode) {
                exitSelectionMode();
              } else {
                setSelectionMode(true);
              }
            }}
            title="Selección múltiple"
            data-testid="selection-mode-toggle"
          >
            <MousePointer2 className="w-4 h-4 mr-1" />
            {selectionMode
              ? `Selección (${selectedBlockIds.size})`
              : 'Selección múltiple'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => undo()}
            disabled={!canUndo}
            title="Deshacer (Ctrl+Z)"
            data-testid="undo-btn"
          >
            <Undo2 className="w-4 h-4" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => redo()}
            disabled={!canRedo}
            title="Rehacer (Ctrl+Shift+Z)"
            data-testid="redo-btn"
          >
            <Redo2 className="w-4 h-4" />
          </Button>
          <Button
            variant={showDictionary ? 'default' : 'outline'}
            size="sm"
            onClick={() => setShowDictionary((v) => !v)}
            title="Panel de diccionario (docentes y asignaturas)"
            data-testid="dictionary-panel-btn"
          >
            <BookOpenCheck className="w-4 h-4 mr-1" />
            Diccionario
          </Button>
          <Button onClick={handleExport} data-testid="export-json-btn">
            <Download className="w-4 h-4 mr-2" />
            Exportar JSON
          </Button>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden bg-slate-50">
        {scheduleData && scheduleData.hojas && scheduleData.hojas.length > 1 ? (
          <Tabs value={currentSheet} onValueChange={loadSheetData} className="w-full flex flex-col">
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

            <div className="flex-1 flex overflow-hidden">
              <div className="flex-1 flex flex-col min-w-0 h-full border-r border-slate-200 bg-white">
                <div className="h-12 border-b border-slate-200 px-4 flex items-center justify-between bg-slate-50/50">
                  <h2 className="text-sm font-semibold text-slate-700">Horario Editable - {currentSheet}</h2>
                </div>
                <div className="flex-1 overflow-auto p-4">
                  <ScheduleGrid key={currentSheet} />
                </div>
              </div>

              <div className="flex-1 flex flex-col min-w-0 h-full bg-white border-r border-slate-200">
                <div className="h-12 border-b border-slate-200 px-4 flex items-center justify-between bg-slate-50/50">
                  <h2 className="text-sm font-semibold text-slate-700">Vista Original - {currentSheet}</h2>
                </div>
                <div className="flex-1 overflow-auto p-4">
                  <ExcelPreview key={currentSheet} />
                </div>
              </div>

              {showDictionary && (
                <div className="w-80 shrink-0 flex flex-col h-full bg-white border-l border-slate-200">
                  <DictionaryPanel scheduleId={scheduleId} onNavigate={handleNavigateFromSearch} />
                </div>
              )}
            </div>
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

            <div className="flex-1 flex flex-col min-w-0 h-full bg-white border-r border-slate-200">
              <div className="h-12 border-b border-slate-200 px-4 flex items-center justify-between bg-slate-50/50">
                <h2 className="text-sm font-semibold text-slate-700">Vista Original</h2>
              </div>
              <div className="flex-1 overflow-auto p-4">
                <ExcelPreview />
              </div>
            </div>

            {showDictionary && (
              <div className="w-80 shrink-0 flex flex-col h-full bg-white border-l border-slate-200">
                <DictionaryPanel scheduleId={scheduleId} onNavigate={handleNavigateFromSearch} />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
