import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Download, ArrowLeft, FileText, Undo2, Redo2, MousePointer2, BookOpenCheck, Upload, ExternalLink, Copy, Check, Lock } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { Badge } from '../components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '../components/ui/dialog';
import { toast } from 'sonner';
import { useSchedule } from '../context/ScheduleContext';
import { useHistory } from '../context/HistoryContext';
import ScheduleGrid from '../components/ScheduleGrid';
import ExcelPreview from '../components/ExcelPreview';
import GlobalSearch from '../components/GlobalSearch';
import DictionaryPanel from '../components/DictionaryPanel';
import { useAuth } from '../context/AuthContext';
import { CollabProvider, useCollab } from '../context/CollabContext';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = BACKEND_URL ? `${BACKEND_URL}/api` : '/api';

const stringToColor = (str) => {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const c = (hash & 0x00FFFFFF).toString(16).toUpperCase();
  return '#' + '00000'.substring(0, 6 - c.length) + c;
};

const getInitials = (name) => {
  if (!name) return '??';
  const parts = name.split('-');
  if (parts.length > 1) return parts[0].substring(0, 1) + parts[1].substring(0, 1);
  return name.substring(0, 2).toUpperCase();
};

const DashboardInner = () => {
  const { scheduleId } = useParams();
  const { scheduleData, setScheduleData, setSubjects, selectionMode, setSelectionMode,
    selectedBlockIds, exitSelectionMode, setExcelHtmlBySheet, excelHtmlBySheet, setLoadingHtmlBySheet } = useSchedule();
  const { canUndo, canRedo, hasUnsavedChanges, undo, redo } = useHistory();
  const [loading, setLoading] = useState(true);
  const [currentSheet, setCurrentSheet] = useState(null);
  const [showDictionary, setShowDictionary] = useState(false);
  
  const { role } = useAuth();
  const { isConnected, requestLock, isSheetLockedByOther, locks, presence, username, forceUnlock, remoteUpdates, notifyUpdate } = useCollab();

  useEffect(() => {
    if (isConnected && currentSheet) {
      requestLock(currentSheet);
    }
  }, [isConnected, currentSheet, requestLock]);

  // Estado del título editable
  const [editableTitle, setEditableTitle] = useState('');
  const [isTitleFocused, setIsTitleFocused] = useState(false);
  const titleInputRef = useRef(null);

  // Estado del diálogo de publicación en R2
  const [publishDialogOpen, setPublishDialogOpen] = useState(false);
  const [publishSemester, setPublishSemester] = useState('');
  const [publishFilename, setPublishFilename] = useState('');
  const [isPublishing, setIsPublishing] = useState(false);
  const [publishedUrl, setPublishedUrl] = useState(null);
  const [urlCopied, setUrlCopied] = useState(false);


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
      console.warn(`Vista HTML no disponible para hoja "${sheetName}":`, err?.response?.status);
    } finally {
      setLoadingHtmlBySheet((prev) => ({ ...prev, [sheetName]: false }));
    }
  }, [scheduleId, setExcelHtmlBySheet, setLoadingHtmlBySheet]);

  // Interceptar mutaciones para notificar a los demás usuarios
  useEffect(() => {
    const reqInterceptor = axios.interceptors.response.use(
      (response) => {
        const method = response.config.method?.toLowerCase();
        if (method && ['post', 'put', 'patch', 'delete'].includes(method)) {
          if (response.config.url.includes(`/api/schedule/${scheduleId}`)) {
            if (currentSheet) notifyUpdate(currentSheet);
          }
        }
        return response;
      },
      (error) => Promise.reject(error)
    );
    return () => {
      axios.interceptors.response.eject(reqInterceptor);
    };
  }, [scheduleId, currentSheet, notifyUpdate]);

  // Reaccionar a cambios remotos
  useEffect(() => {
    if (remoteUpdates && remoteUpdates.length > 0) {
      const lastUpdate = remoteUpdates[remoteUpdates.length - 1];
      toast.info(`Sincronizando cambios de ${lastUpdate.byUser}...`);
      
      axios.get(`${API}/schedule/${scheduleId}`).then(res => {
        let updated = res.data;
        if (currentSheet && res.data.hojas_data && res.data.hojas_data[currentSheet]) {
          const sheetData = res.data.hojas_data[currentSheet];
          updated = {
            ...res.data,
            hoja_actual: currentSheet,
            celdas: sheetData.celdas || [],
            estructura_dias: sheetData.estructura_dias || [],
            estructura_horas: sheetData.estructura_horas || [],
            excel_preview: sheetData.excel_preview || [],
          };
          if (lastUpdate.sheet === currentSheet) {
            loadSheetHtml(currentSheet);
          }
        }
        setScheduleData(updated);
      }).catch(err => console.error("Error syncing remote update", err));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [remoteUpdates]);

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

        // Inicializar título editable con el nombre del archivo
        const initialTitle = scheduleRes.data.nombre_archivo || 'Horario';
        setEditableTitle(initialTitle);
        // Pre-llenar el campo de nombre en el diálogo de publicación
        setPublishFilename(initialTitle);

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
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
    // Usa el título editable como nombre de archivo
    const safeName = (editableTitle || scheduleData?.nombre_archivo || `horario_${scheduleId}`)
      .replace(/[^a-zA-Z0-9_\-\. ]/g, '')
      .replace(/\s+/g, '_');
    const filename = safeName.endsWith('.json') ? safeName : `${safeName}.json`;
    try {
      const response = await axios.post(`${API}/schedule/${scheduleId}/export`);
      const blob = new Blob([JSON.stringify(response.data, null, 2)], {
        type: 'application/json',
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      toast.success(`Descargado como "${filename}"`);
    } catch (error) {
      console.error('Error exporting schedule:', error);
      toast.error('Error al exportar el horario');
    }
  };

  const handleOpenPublishDialog = () => {
    // Pre-llenar el nombre con el título editable actual
    setPublishFilename(editableTitle || scheduleData?.nombre_archivo || '');
    setPublishedUrl(null);
    setUrlCopied(false);
    setPublishDialogOpen(true);
  };

  const handlePublish = async () => {
    if (!publishSemester.trim()) {
      toast.error('Ingresa el semestre antes de publicar');
      return;
    }
    if (!publishFilename.trim()) {
      toast.error('Ingresa el nombre del archivo antes de publicar');
      return;
    }
    setIsPublishing(true);
    try {
      const response = await axios.post(`${API}/schedule/${scheduleId}/publish`, {
        semester: publishSemester.trim(),
        filename: publishFilename.trim(),
      });
      setPublishedUrl(response.data.url);
      toast.success('¡Oferta publicada exitosamente en Cloudflare R2!');
    } catch (error) {
      const detail = error?.response?.data?.detail || 'Error desconocido';
      console.error('Error publicando en R2:', error);
      toast.error(`Error al publicar: ${detail}`);
    } finally {
      setIsPublishing(false);
    }
  };

  const handleCopyUrl = async () => {
    if (publishedUrl) {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        try {
          await navigator.clipboard.writeText(publishedUrl);
          setUrlCopied(true);
          setTimeout(() => setUrlCopied(false), 2000);
          return;
        } catch (err) {
          console.error("Error copiando con API clipboard:", err);
        }
      }
      
      // Fallback para entornos donde clipboard no está disponible (ej. IP sin HTTPS)
      try {
        const textArea = document.createElement("textarea");
        textArea.value = publishedUrl;
        textArea.style.position = "fixed";
        textArea.style.left = "-9999px";
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        const successful = document.execCommand('copy');
        if (successful) {
          setUrlCopied(true);
          setTimeout(() => setUrlCopied(false), 2000);
        } else {
          toast.error("No se pudo copiar automáticamente");
        }
        document.body.removeChild(textArea);
      } catch (err) {
        console.error('Fallback error:', err);
        toast.error("Error al copiar el enlace");
      }
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
      {/* Diálogo de publicación en Cloudflare R2 */}
      <Dialog open={publishDialogOpen} onOpenChange={(open) => {
        if (!isPublishing) {
          setPublishDialogOpen(open);
          if (!open) setPublishedUrl(null);
        }
      }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Publicar en Cloudflare R2</DialogTitle>
            <DialogDescription>
              El archivo JSON se publicará en el bucket de R2 y estará disponible inmediatamente
              en el proyecto principal de horarios.
            </DialogDescription>
          </DialogHeader>

          {!publishedUrl ? (
            <div className="flex flex-col gap-4 py-2">
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-slate-700" htmlFor="publish-semester">
                  Semestre
                </label>
                <input
                  id="publish-semester"
                  type="text"
                  placeholder="ej. 2026-1"
                  value={publishSemester}
                  onChange={(e) => setPublishSemester(e.target.value)}
                  disabled={isPublishing}
                  className="border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium text-slate-700" htmlFor="publish-filename">
                  Nombre del archivo
                </label>
                <input
                  id="publish-filename"
                  type="text"
                  placeholder="ej. ingenieria_de_sistemas"
                  value={publishFilename}
                  onChange={(e) => setPublishFilename(e.target.value)}
                  disabled={isPublishing}
                  className="border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                />
                <p className="text-xs text-slate-500">
                  Se guardará como: <code className="bg-slate-100 px-1 rounded">{publishSemester || 'semestre'}/{publishFilename || 'archivo'}.json</code>
                </p>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-3 py-2">
              <div className="flex items-center gap-2 text-green-600 font-medium">
                <Check className="w-5 h-5" />
                Publicado exitosamente
              </div>
              <div className="flex items-center gap-2 border border-slate-200 rounded-md p-2 bg-slate-50 overflow-hidden">
                <span className="text-xs text-slate-600 flex-1 truncate font-mono min-w-0" title={publishedUrl}>{publishedUrl}</span>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={handleCopyUrl}
                  title="Copiar URL"
                  data-testid="copy-r2-url-btn"
                >
                  {urlCopied ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
                </Button>
                <a href={publishedUrl} target="_blank" rel="noopener noreferrer">
                  <Button size="sm" variant="ghost" title="Abrir en nueva pestaña">
                    <ExternalLink className="w-4 h-4" />
                  </Button>
                </a>
              </div>
              <p className="text-xs text-slate-500">
                El archivo ya está disponible en el proyecto principal. Puedes republicar
                con otro nombre o cerrar este diálogo.
              </p>
            </div>
          )}

          <DialogFooter>
            {!publishedUrl ? (
              <>
                <Button
                  variant="outline"
                  onClick={() => setPublishDialogOpen(false)}
                  disabled={isPublishing}
                >
                  Cancelar
                </Button>
                <Button
                  onClick={handlePublish}
                  disabled={isPublishing || !publishSemester.trim() || !publishFilename.trim()}
                  data-testid="confirm-publish-btn"
                >
                  {isPublishing ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2" />
                      Publicando...
                    </>
                  ) : (
                    <>
                      <Upload className="w-4 h-4 mr-2" />
                      Publicar en R2
                    </>
                  )}
                </Button>
              </>
            ) : (
              <Button onClick={() => {
                setPublishDialogOpen(false);
                setPublishedUrl(null);
              }}>
                Cerrar
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <header className="h-16 border-b border-slate-200 px-6 flex items-center justify-between bg-white z-50 sticky top-0">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => window.history.back()} data-testid="back-btn">
            <ArrowLeft className="w-4 h-4 mr-2" />
            Volver
          </Button>
          <div>
            <div className="flex items-center gap-2">
              {/* Título editable inline */}
              <input
                ref={titleInputRef}
                type="text"
                value={editableTitle}
                onChange={(e) => {
                  setEditableTitle(e.target.value);
                  setPublishFilename(e.target.value);
                }}
                onFocus={() => setIsTitleFocused(true)}
                onBlur={() => setIsTitleFocused(false)}
                className={`text-xl font-semibold text-slate-900 bg-transparent border-0 outline-none focus:bg-slate-50 focus:border focus:border-slate-300 rounded px-1 py-0.5 transition-all min-w-0 max-w-xs ${
                  isTitleFocused ? 'border border-slate-300 bg-slate-50 shadow-sm' : ''
                }`}
                title="Haz clic para editar el nombre del archivo"
                data-testid="schedule-title-input"
              />
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
          {/* PRESENCIA VISUAL */}
          {presence && presence.length > 0 && (
            <div className="flex items-center mr-4" title="Usuarios editando este horario">
              {presence.map(user => (
                <div
                  key={user}
                  className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold border-2 border-white -ml-2 shadow-sm"
                  style={{ backgroundColor: stringToColor(user) }}
                  title={user === username ? `${user} (Tú)` : user}
                >
                  {getInitials(user)}
                </div>
              ))}
            </div>
          )}
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
          {/* Botón descargar local */}
          <Button
            variant="outline"
            onClick={handleExport}
            title="Descargar JSON localmente"
            data-testid="export-json-btn"
          >
            <Download className="w-4 h-4 mr-2" />
            Descargar
          </Button>
          {/* Botón publicar en R2 */}
          {role === 'admin' && (
            <Button
              onClick={handleOpenPublishDialog}
              title="Publicar oferta en Cloudflare R2"
              data-testid="publish-r2-btn"
            >
              <Upload className="w-4 h-4 mr-2" />
              Publicar
            </Button>
          )}
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
                    {isSheetLockedByOther(hoja) ? (
                      <button
                        title={role === 'admin' ? `Bloqueado por ${locks[hoja]}. Doble clic para FORZAR DESBLOQUEO (Admin)` : `Bloqueado por ${locks[hoja]}`}
                        onDoubleClick={(e) => { 
                          e.stopPropagation(); 
                          if(role === 'admin') {
                            forceUnlock(hoja); 
                            toast.success('Forzando desbloqueo...');
                          } 
                        }}
                        className={`p-0 border-0 bg-transparent flex items-center justify-center ${role === 'admin' ? 'cursor-pointer hover:bg-slate-100' : 'cursor-default'} rounded`}
                      >
                        <Lock className="w-4 h-4 text-amber-500" />
                      </button>
                    ) : (
                      <FileText className="w-4 h-4" />
                    )}
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

const Dashboard = () => {
  const { scheduleId } = useParams();
  return (
    <CollabProvider scheduleId={scheduleId}>
      <DashboardInner />
    </CollabProvider>
  );
};

export default Dashboard;
