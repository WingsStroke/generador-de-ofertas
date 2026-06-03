import React, { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from './ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from './ui/tabs';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Badge } from './ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { toast } from 'sonner';
import { useSchedule } from '../context/ScheduleContext';
import { useHistory } from '../context/HistoryContext';
import { Search, Trash2, Plus, Clock, Calendar, Save, CheckCircle2, Sparkles } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = BACKEND_URL ? `${BACKEND_URL}/api` : '/api';

const cleanNoise = (text) => {
  if (!text) return '';
  return text
    .replace(/\r?\n/g, ' ')
    .replace(/[\u2013\u2014]/g, '-')
    .replace(/\s+/g, ' ')
    .replace(/^[\s\-_,;/|]+|[\s\-_,;/|]+$/g, '')
    .trim();
};

const BlockEditor = ({ block, onClose }) => {
  const { scheduleId } = useParams();
  const { scheduleData, setScheduleData, subjects } = useSchedule();
  const { pushAction } = useHistory();
  const [formData, setFormData] = useState({
    materia: block.materia || '',
    materia_id: block.materia_id || '',
    grupo: block.grupo || '',
    docente: block.docente || '',
    aula: block.aula || '',
  });
  const [newHorario, setNewHorario] = useState({ dia: '', hora_inicio: '' });
  const [isAddingHorario, setIsAddingHorario] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [searching, setSearching] = useState(false);
  const [activeTab, setActiveTab] = useState('info');
  const [savingTeacher, setSavingTeacher] = useState(false);
  const [teacherSaved, setTeacherSaved] = useState(false);
  const suggestionsRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (suggestionsRef.current && !suggestionsRef.current.contains(e.target)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    const searchSubjects = async () => {
      if (formData.materia.length < 2) {
        setSuggestions([]);
        return;
      }

      setSearching(true);
      try {
        const programId = scheduleData?.programa_id || 'ingenieria_de_sistemas';
        const response = await axios.get(
          `${API}/subjects/search/${encodeURIComponent(formData.materia)}?program_id=${programId}`
        );
        setSuggestions(response.data);
      } catch (error) {
        console.error('Error searching subjects:', error);
      } finally {
        setSearching(false);
      }
    };

    const timer = setTimeout(searchSubjects, 300);
    return () => clearTimeout(timer);
  }, [formData.materia, scheduleData]);

  const handleChange = (field, value) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
    if (field === 'materia') {
      setShowSuggestions(true);
    }
  };

  const handleSelectSuggestion = (subject) => {
    setFormData((prev) => ({
      ...prev,
      materia: subject.nombre,
      materia_id: subject.id,
    }));
    setShowSuggestions(false);
  };

  const handleSaveTeacher = async () => {
    if (!formData.docente || formData.docente.trim().length < 3) {
      toast.error('Nombre de docente inválido');
      return;
    }
    setSavingTeacher(true);
    try {
      const response = await axios.post(`${API}/teachers`, { name: formData.docente });
      if (response.data.added) {
        toast.success(response.data.message);
      } else {
        toast.info(response.data.message);
      }
      setTeacherSaved(true);
      // Actualizar el origen del docente en el bloque actual
      if (block) {
        block.origen_docente = "diccionario";
      }
    } catch (error) {
      console.error('Error saving teacher:', error);
      toast.error('Error al guardar el docente');
    } finally {
      setSavingTeacher(false);
    }
  };

  const handleSave = async () => {
    // Capturar estado anterior para undo
    const previousSchedule = JSON.parse(JSON.stringify(scheduleData));

    try {
      // Intentar localizar la celda por block.id en estado actual; fallback a día/hora
      const findCellByBlock = (data) =>
        data?.celdas?.find((c) => (c.bloques || []).some((b) => b.id === block.id));

      let cellData = findCellByBlock(scheduleData) || scheduleData.celdas.find(
        (c) => c.dia === getCellDia() && c.hora_inicio === getCellHoraInicio()
      );

      const doPut = async () =>
        axios.put(
          `${API}/schedule/${scheduleId}/cell/${cellData?.dia || 'L'}/${cellData?.hora_inicio || '00:00'}/block/${block.id}`,
          formData
        );

      try {
        await doPut();
      } catch (err) {
        // Si el bloque/horario no se encontró, refrescar y reintentar una vez
        if (err?.response?.status === 404) {
          try {
            const fresh = await axios.get(`${API}/schedule/${scheduleId}`);
            const hoja = fresh.data.hoja_actual || (fresh.data.hojas && fresh.data.hojas[0]);
            const sheetData = fresh.data.hojas_data?.[hoja];
            const refreshed = {
              ...fresh.data,
              hoja_actual: hoja,
              celdas: sheetData?.celdas || fresh.data.celdas || [],
              estructura_dias: sheetData?.estructura_dias || fresh.data.estructura_dias || [],
              estructura_horas: sheetData?.estructura_horas || fresh.data.estructura_horas || [],
              excel_preview: sheetData?.excel_preview || fresh.data.excel_preview || [],
            };
            setScheduleData(refreshed);
            cellData = findCellByBlock(refreshed);
            if (!cellData) {
              toast.error('El bloque ya no existe. Horario actualizado.');
              onClose();
              return;
            }
            await doPut();
          } catch (retryErr) {
            throw retryErr;
          }
        } else {
          throw err;
        }
      }

      // Aplicar mutación local directa para no pisar cambios en memoria no persistidos.
      // El backend ya actualizó el bloque; no hacemos refetch para evitar perder ediciones
      // previas (movimientos, etc.) que solo viven en el estado local del frontend.
      const updatedSchedule = JSON.parse(JSON.stringify(scheduleData));
      const currentSheet = updatedSchedule.hoja_actual;

      const applyBlockUpdate = (celdas) => {
        if (!celdas) return;
        const cell = celdas.find(
          (c) => c.dia === cellData.dia && c.hora_inicio === cellData.hora_inicio
        );
        if (cell) {
          const blockIndex = cell.bloques.findIndex((b) => b.id === block.id);
          if (blockIndex !== -1) {
            cell.bloques[blockIndex] = {
              ...cell.bloques[blockIndex],
              ...formData,
              estado: 'confirmed',
              nivel_confianza: 1.0,
            };
          }
        }
      };

      // Actualizar en celdas top-level
      applyBlockUpdate(updatedSchedule.celdas);

      // Actualizar también en hojas_data para consistencia al cambiar de pestaña
      if (updatedSchedule.hojas_data && currentSheet && updatedSchedule.hojas_data[currentSheet]) {
        applyBlockUpdate(updatedSchedule.hojas_data[currentSheet].celdas);
      }

      setScheduleData(updatedSchedule);

      // Registrar en historial
      pushAction({
        type: 'UPDATE_BLOCK',
        description: `Editar: ${formData.materia || 'Bloque'}`,
        onUndo: () => {
          setScheduleData(previousSchedule);
          axios.put(`${API}/schedule/${scheduleId}/state`, previousSchedule).catch(console.error);
        },
        onRedo: () => {
          setScheduleData(updatedSchedule);
          axios.put(`${API}/schedule/${scheduleId}/state`, updatedSchedule).catch(console.error);
        },
      });

      toast.success('Bloque actualizado exitosamente');
      onClose();
    } catch (error) {
      console.error('Error updating block:', error);
      const status = error?.response?.status;
      const detail = error?.response?.data?.detail;
      if (status === 404) {
        toast.error(detail || 'No se encontró el bloque en el servidor. Recarga la página.');
      } else {
        toast.error(`Error al actualizar el bloque${status ? ` (${status})` : ''}`);
      }
    }
  };

  const getRelatedBlocks = () => {
    if (!scheduleData) return [];
    const related = [];
    const currentSheet = scheduleData.hoja_actual;
    const celdas = scheduleData.hojas_data?.[currentSheet]?.celdas || scheduleData.celdas || [];
    
    celdas.forEach(cell => {
      (cell.bloques || []).forEach(b => {
        const isSame = formData.materia_id 
          ? (b.materia_id === formData.materia_id && b.grupo === formData.grupo)
          : (b.materia === formData.materia && b.grupo === formData.grupo);
          
        if (isSame) {
          related.push({
            id: b.id,
            dia: cell.dia,
            hora_inicio: cell.hora_inicio,
            hora_fin: cell.hora_fin
          });
        }
      });
    });
    
    // Ordenar cronológicamente (simplificado)
    return related.sort((a, b) => a.dia.localeCompare(b.dia) || a.hora_inicio.localeCompare(b.hora_inicio));
  };

  const handleAddRelatedBlock = async () => {
    if (!newHorario.dia || !newHorario.hora_inicio) {
      toast.error('Selecciona día y hora');
      return;
    }
    
    setIsAddingHorario(true);
    const previousSchedule = JSON.parse(JSON.stringify(scheduleData));
    
    try {
      const horaObj = scheduleData.estructura_horas.find(h => h.inicio === newHorario.hora_inicio);
      
      const response = await axios.post(`${API}/schedule/${scheduleId}/block`, {
        sheet: scheduleData.hoja_actual,
        dia: newHorario.dia,
        hora_inicio: newHorario.hora_inicio,
        hora_fin: horaObj?.fin || newHorario.hora_inicio,
        materia: formData.materia,
        materia_id: formData.materia_id || null,
        grupo: formData.grupo || null,
        docente: formData.docente || null,
        aula: formData.aula || null,
      });

      const newBlock = response.data.block;
      const updatedSchedule = JSON.parse(JSON.stringify(scheduleData));
      const hoja = updatedSchedule.hoja_actual;
      
      const applyNewBlock = (celdasList) => {
        if (!celdasList) return;
        let cell = celdasList.find(
          (c) => c.dia === newHorario.dia && c.hora_inicio === newHorario.hora_inicio
        );
        if (cell) {
          cell.bloques = cell.bloques || [];
          cell.bloques.push(newBlock);
        } else {
          celdasList.push({
            dia: newHorario.dia,
            hora_inicio: newHorario.hora_inicio,
            hora_fin: horaObj?.fin || newHorario.hora_inicio,
            bloques: [newBlock],
            celda_ref: null,
          });
        }
      };

      applyNewBlock(updatedSchedule.celdas);
      if (updatedSchedule.hojas_data && hoja && updatedSchedule.hojas_data[hoja]) {
        applyNewBlock(updatedSchedule.hojas_data[hoja].celdas);
      }

      setScheduleData(updatedSchedule);
      setNewHorario({ dia: '', hora_inicio: '' });
      toast.success('Horario añadido');
      
      pushAction({
        type: 'CREATE_BLOCK',
        description: `Añadir horario: ${formData.materia}`,
        payload: { blockId: newBlock.id },
        onUndo: () => {
          setScheduleData(previousSchedule);
          axios.put(`${API}/schedule/${scheduleId}/state`, previousSchedule).catch(console.error);
        },
        onRedo: () => {
          setScheduleData(updatedSchedule);
          axios.put(`${API}/schedule/${scheduleId}/state`, updatedSchedule).catch(console.error);
        },
      });

    } catch (e) {
      console.error(e);
      toast.error('Error al agregar el bloque');
    } finally {
      setIsAddingHorario(false);
    }
  };

  const handleDeleteRelatedBlock = async (idToDelete, celdaDia, celdaHoraInicio) => {
    const related = getRelatedBlocks();
    if (related.length <= 1) {
      toast.error('No puedes eliminar el único horario desde aquí. Usa el botón "Eliminar" general.');
      return;
    }
    
    const previousSchedule = JSON.parse(JSON.stringify(scheduleData));
    try {
      await axios.delete(
        `${API}/schedule/${scheduleId}/cell/${celdaDia}/${celdaHoraInicio}/block/${idToDelete}`
      );
      
      const updatedSchedule = JSON.parse(JSON.stringify(scheduleData));
      const currentSheet = updatedSchedule.hoja_actual;
      
      const applyDelete = (celdasList) => {
        if (!celdasList) return;
        const cell = celdasList.find((c) => c.dia === celdaDia && c.hora_inicio === celdaHoraInicio);
        if (cell) {
          cell.bloques = cell.bloques.filter(b => b.id !== idToDelete);
        }
      };
      
      applyDelete(updatedSchedule.celdas);
      if (updatedSchedule.hojas_data && currentSheet && updatedSchedule.hojas_data[currentSheet]) {
        applyDelete(updatedSchedule.hojas_data[currentSheet].celdas);
      }
      
      setScheduleData(updatedSchedule);
      toast.success('Horario removido');
      
      pushAction({
        type: 'DELETE_BLOCK',
        description: `Remover horario: ${formData.materia}`,
        payload: { blockId: idToDelete },
        onUndo: () => {
          setScheduleData(previousSchedule);
          axios.put(`${API}/schedule/${scheduleId}/state`, previousSchedule).catch(console.error);
        },
        onRedo: () => {
          setScheduleData(updatedSchedule);
          axios.put(`${API}/schedule/${scheduleId}/state`, updatedSchedule).catch(console.error);
        },
      });
      
      // If we just deleted the block we are currently editing, close the editor
      if (idToDelete === block.id) {
        onClose();
      }
    } catch (e) {
      console.error(e);
      toast.error('Error al remover el bloque');
    }
  };

  const handleDelete = async () => {
    // Guardar estado anterior para undo (con el bloque incluido, copia profunda)
    const previousSchedule = JSON.parse(JSON.stringify(scheduleData));

    // Guardar datos del bloque para poder recrearlo en redo
    const blockData = JSON.parse(JSON.stringify(block));

    // Buscar la celda en celdas top-level (hoja actual)
    const cellData = scheduleData.celdas.find(
      (c) => c.bloques && c.bloques.some((b) => b.id === block.id)
    );
    const dia = cellData?.dia;
    const horaInicio = cellData?.hora_inicio;
    const horaFin = cellData?.hora_fin;
    const currentSheet = scheduleData.hoja_actual;

    try {
      await axios.delete(
        `${API}/schedule/${scheduleId}/cell/${cellData.dia}/${cellData.hora_inicio}/block/${block.id}`
      );

      // Construir estado actualizado con el bloque eliminado tanto en celdas como en hojas_data
      const updatedSchedule = JSON.parse(JSON.stringify(scheduleData));

      // Actualizar celdas top-level
      const topCell = updatedSchedule.celdas.find(
        (c) => c.dia === cellData.dia && c.hora_inicio === cellData.hora_inicio
      );
      if (topCell) topCell.bloques = topCell.bloques.filter((b) => b.id !== block.id);

      // Actualizar también en hojas_data para mantener consistencia al cambiar de pestaña
      if (updatedSchedule.hojas_data && currentSheet && updatedSchedule.hojas_data[currentSheet]) {
        const sheetCells = updatedSchedule.hojas_data[currentSheet].celdas;
        const sheetCell = sheetCells?.find(
          (c) => c.dia === cellData.dia && c.hora_inicio === cellData.hora_inicio
        );
        if (sheetCell) sheetCell.bloques = sheetCell.bloques.filter((b) => b.id !== block.id);
      }

      setScheduleData(updatedSchedule);

      // Registrar en historial
      pushAction({
        type: 'DELETE_BLOCK',
        description: `Eliminar: ${blockData.materia || 'Bloque'}`,
        payload: {
          blockId: block.id,
          blockData,
          cellSlot: { dia, hora_inicio: horaInicio, hora_fin: horaFin },
        },
        onUndo: () => {
          // Restaurar estado anterior completo (incluye hojas_data y celdas)
          setScheduleData(previousSchedule);
          axios.put(`${API}/schedule/${scheduleId}/state`, previousSchedule).catch(console.error);
        },
        onRedo: () => {
          // Volver a aplicar la eliminación (ya calculada)
          setScheduleData(updatedSchedule);
          axios.put(`${API}/schedule/${scheduleId}/state`, updatedSchedule).catch(console.error);
        },
      });

      toast.success('Bloque eliminado exitosamente');
      onClose();
    } catch (error) {
      console.error('Error deleting block:', error);
      toast.error('Error al eliminar el bloque');
    }
  };

  const getCellDia = () => {
    const cell = scheduleData.celdas.find((c) =>
      c.bloques.some((b) => b.id === block.id)
    );
    return cell?.dia;
  };

  const getCellHoraInicio = () => {
    const cell = scheduleData.celdas.find((c) =>
      c.bloques.some((b) => b.id === block.id)
    );
    return cell?.hora_inicio;
  };

  const getStatusBadge = () => {
    const statusMap = {
      confirmed: { label: 'Confirmado', color: 'bg-green-100 text-green-800' },
      inferred: { label: 'Inferido', color: 'bg-yellow-100 text-yellow-800' },
      error: { label: 'Error', color: 'bg-red-100 text-red-800' },
      unknown: { label: 'Desconocido', color: 'bg-gray-100 text-gray-800' },
    };
    const status = statusMap[block.estado] || statusMap.unknown;
    return (
      <Badge className={status.color} variant="outline">
        {status.label}
      </Badge>
    );
  };


  const DIAS_OPCIONES = [
    { value: 'L', label: 'Lunes' },
    { value: 'M', label: 'Martes' },
    { value: 'X', label: 'Miércoles' },
    { value: 'J', label: 'Jueves' },
    { value: 'V', label: 'Viernes' },
    { value: 'S', label: 'Sábado' },
    { value: 'D', label: 'Domingo' },
  ];

  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent 
        className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto" 
        data-testid="edit-block-dialog"
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !showSuggestions) {
            e.preventDefault();
            handleSave();
          }
        }}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between">
            <span>Editar Bloque</span>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 text-xs px-2 text-blue-600 hover:text-blue-700 border-blue-200 bg-blue-50/50"
                onClick={() => {
                  setFormData(prev => ({
                    materia: cleanNoise(prev.materia),
                    materia_id: prev.materia_id,
                    grupo: cleanNoise(prev.grupo),
                    docente: cleanNoise(prev.docente),
                    aula: cleanNoise(prev.aula)
                  }));
                  toast.success("Campos normalizados con éxito");
                }}
                title="Limpiar ruido de todos los campos (quitar dobles espacios, saltos de línea y guiones huérfanos)"
              >
                <Sparkles className="w-3.5 h-3.5 mr-1" />
                Limpiar ruido
              </Button>
              {getStatusBadge()}
            </div>
          </DialogTitle>
          <DialogDescription>
            Edita la información del bloque y, si lo necesitas, ajusta manualmente los intervalos de 50 minutos en la pestaña "Horarios".
          </DialogDescription>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full" data-testid="block-editor-tabs">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="info" data-testid="tab-info">
              <Calendar className="w-4 h-4 mr-2" />
              Información
            </TabsTrigger>
            <TabsTrigger value="horarios" data-testid="tab-horarios">
              <Clock className="w-4 h-4 mr-2" />
              Horarios
              <Badge variant="secondary" className="ml-2 text-xs" data-testid="horarios-count-badge">
                {getRelatedBlocks().length}
              </Badge>
            </TabsTrigger>
          </TabsList>

          <TabsContent value="info" className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="materia">Materia</Label>
              <div className="relative">
                <Input
                  id="materia"
                  value={formData.materia}
                  onChange={(e) => handleChange('materia', e.target.value)}
                  onFocus={() => formData.materia.length >= 2 && setShowSuggestions(true)}
                  onBlur={(e) => {
                    const cleaned = cleanNoise(e.target.value);
                    if (cleaned !== e.target.value) {
                      handleChange('materia', cleaned);
                    }
                  }}
                  placeholder="Buscar materia..."
                  data-testid="materia-input"
                />
                {searching && (
                  <div className="absolute right-3 top-3">
                    <Search className="w-4 h-4 animate-spin text-slate-400" />
                  </div>
                )}
                {showSuggestions && suggestions.length > 0 && (
                  <div ref={suggestionsRef} className="absolute z-50 w-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-60 overflow-auto">
                    {suggestions.map((subject) => (
                      <button
                        key={subject.id}
                        type="button"
                        className="w-full text-left px-3 py-2 hover:bg-slate-50 transition-colors text-sm"
                        onClick={() => handleSelectSuggestion(subject)}
                        data-testid={`suggestion-${subject.id}`}
                      >
                        <div className="font-medium text-slate-900">
                          {subject.nombre}
                        </div>
                        <div className="text-xs text-slate-500">
                          {subject.codigo && `${subject.codigo} • `}
                          Confianza: {(subject.confidence * 100).toFixed(0)}%
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="grupo">Grupo</Label>
              <Input
                id="grupo"
                value={formData.grupo}
                onChange={(e) => handleChange('grupo', e.target.value)}
                onBlur={(e) => {
                  const cleaned = cleanNoise(e.target.value);
                  if (cleaned !== e.target.value) {
                    handleChange('grupo', cleaned);
                  }
                }}
                placeholder="Ej: A1, B2"
                data-testid="grupo-input"
              />
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Label htmlFor="docente">Docente</Label>
                  {block.origen_docente === 'diccionario' || teacherSaved ? (
                    <Badge variant="outline" className="text-[10px] h-4 bg-blue-50 text-blue-700 border-blue-200">
                      Diccionario
                    </Badge>
                  ) : (
                    block.docente && (
                      <Badge variant="outline" className="text-[10px] h-4 bg-orange-50 text-orange-700 border-orange-200">
                        Motor
                      </Badge>
                    )
                  )}
                </div>
                {formData.docente && formData.docente.trim().length > 3 && block.origen_docente !== 'diccionario' && !teacherSaved && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-6 text-xs px-2 text-blue-600 hover:text-blue-800 hover:bg-blue-50"
                    onClick={handleSaveTeacher}
                    disabled={savingTeacher}
                  >
                    {savingTeacher ? (
                      <span className="animate-pulse">Guardando...</span>
                    ) : (
                      <>
                        <Save className="w-3 h-3 mr-1" />
                        Guardar al diccionario
                      </>
                    )}
                  </Button>
                )}
              </div>
              <Input
                id="docente"
                value={formData.docente}
                onChange={(e) => {
                  handleChange('docente', e.target.value);
                  setTeacherSaved(false);
                }}
                onBlur={(e) => {
                  const cleaned = cleanNoise(e.target.value);
                  if (cleaned !== e.target.value) {
                    handleChange('docente', cleaned);
                  }
                }}
                placeholder="Nombre del docente"
                data-testid="docente-input"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="aula">Aula</Label>
              <Input
                id="aula"
                value={formData.aula}
                onChange={(e) => handleChange('aula', e.target.value)}
                onBlur={(e) => {
                  const cleaned = cleanNoise(e.target.value);
                  if (cleaned !== e.target.value) {
                    handleChange('aula', cleaned);
                  }
                }}
                placeholder="Laboratorio, salón, etc."
                data-testid="aula-input"
              />
            </div>

            {block.texto_original && (
              <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
                <p className="text-xs text-slate-500 mb-1">Texto original:</p>
                <p className="text-xs text-slate-700 font-mono">
                  {block.texto_original}
                </p>
              </div>
            )}
          </TabsContent>

          <TabsContent value="horarios" className="space-y-4 py-4" data-testid="horarios-tab-content">
            <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
              <p className="text-xs text-blue-800">
                <strong>Información:</strong> Todos los bloques de <strong>{formData.materia}</strong> en el grupo <strong>{formData.grupo || '(Sin grupo)'}</strong>. Si agregas o eliminas aquí, se crean o borran celdas en el horario original de forma global.
              </p>
            </div>

            <div className="space-y-3">
              {getRelatedBlocks().map((rb, idx) => (
                <div key={rb.id} className="flex items-center justify-between p-3 border border-slate-200 rounded-lg bg-white shadow-sm">
                  <div className="flex items-center gap-3">
                    <Badge variant="outline" className="w-8 justify-center shrink-0">
                      #{idx + 1}
                    </Badge>
                    <div>
                      <p className="text-sm font-medium text-slate-800">{rb.dia}</p>
                      <p className="text-xs text-slate-500">{rb.hora_inicio} - {rb.hora_fin}</p>
                    </div>
                  </div>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-8 w-8 text-red-500 hover:text-red-700 hover:bg-red-50"
                    onClick={() => handleDeleteRelatedBlock(rb.id, rb.dia, rb.hora_inicio)}
                    title="Eliminar este horario"
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              ))}
            </div>

            <div className="mt-4 pt-4 border-t border-slate-200">
              <h4 className="text-sm font-medium text-slate-900 mb-3">Agregar nueva franja horaria</h4>
              <div className="flex gap-2 items-end">
                <div className="flex-1 space-y-1">
                  <Label className="text-xs">Día</Label>
                  <Select value={newHorario.dia} onValueChange={(v) => setNewHorario(p => ({ ...p, dia: v }))}>
                    <SelectTrigger className="h-9">
                      <SelectValue placeholder="Seleccionar..." />
                    </SelectTrigger>
                    <SelectContent>
                      {DIAS_OPCIONES.map((d) => (
                        <SelectItem key={d.value} value={d.value}>{d.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex-1 space-y-1">
                  <Label className="text-xs">Hora Inicio</Label>
                  <Select value={newHorario.hora_inicio} onValueChange={(v) => setNewHorario(p => ({ ...p, hora_inicio: v }))}>
                    <SelectTrigger className="h-9">
                      <SelectValue placeholder="Seleccionar..." />
                    </SelectTrigger>
                    <SelectContent>
                      {scheduleData?.estructura_horas?.map((h) => (
                        <SelectItem key={h.inicio} value={h.inicio}>{h.inicio}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <Button 
                  onClick={handleAddRelatedBlock}
                  disabled={isAddingHorario || !newHorario.dia || !newHorario.hora_inicio}
                  className="h-9"
                >
                  <Plus className="w-4 h-4 mr-1" />
                  Agregar
                </Button>
              </div>
            </div>
          </TabsContent>
        </Tabs>

        <DialogFooter>
          <Button
            variant="destructive"
            onClick={handleDelete}
            data-testid="delete-block-btn"
          >
            <Trash2 className="w-4 h-4 mr-2" />
            Eliminar
          </Button>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={handleSave} data-testid="save-block-btn">
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default BlockEditor;
