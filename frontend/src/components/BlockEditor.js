import React, { useState, useEffect } from 'react';
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
import { Search, Trash2, Plus, Clock, Calendar } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const BlockEditor = ({ block, onClose }) => {
  const { scheduleId } = useParams();
  const { scheduleData, setScheduleData, subjects } = useSchedule();
  const [formData, setFormData] = useState({
    materia: block.materia || '',
    materia_id: block.materia_id || '',
    grupo: block.grupo || '',
    docente: block.docente || '',
    aula: block.aula || '',
  });
  const [horarios, setHorarios] = useState(block.horarios || []);
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [searching, setSearching] = useState(false);
  const [activeTab, setActiveTab] = useState('info');

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

  const handleSave = async () => {
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

      await axios.put(
        `${API}/schedule/${scheduleId}/block/${block.id}/horarios`,
        horarios
      );

      const updatedSchedule = { ...scheduleData };
      const cell = updatedSchedule.celdas.find(
        (c) => c.dia === cellData.dia && c.hora_inicio === cellData.hora_inicio
      );
      if (cell) {
        const blockIndex = cell.bloques.findIndex((b) => b.id === block.id);
        if (blockIndex !== -1) {
          cell.bloques[blockIndex] = {
            ...cell.bloques[blockIndex],
            ...formData,
            horarios,
            estado: 'confirmed',
            nivel_confianza: 1.0,
          };
        }
      }

      setScheduleData(updatedSchedule);
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

  const handleAddHorario = () => {
    setHorarios([
      ...horarios,
      {
        dia: 'L',
        hora_inicio: '08:00',
        hora_fin: '08:50',
        bloques_cantidad: 1,
      },
    ]);
  };

  const handleRemoveHorario = (index) => {
    setHorarios(horarios.filter((_, i) => i !== index));
  };

  const handleUpdateHorario = (index, field, value) => {
    const newHorarios = [...horarios];
    newHorarios[index][field] = value;
    
    if (field === 'hora_inicio' || field === 'hora_fin') {
      const inicio = field === 'hora_inicio' ? value : newHorarios[index].hora_inicio;
      const fin = field === 'hora_fin' ? value : newHorarios[index].hora_fin;
      newHorarios[index].bloques_cantidad = calcularBloques(inicio, fin);
    }
    
    setHorarios(newHorarios);
  };

  const calcularBloques = (inicio, fin) => {
    try {
      const [hI, mI] = inicio.split(':').map(Number);
      const [hF, mF] = fin.split(':').map(Number);
      const minutos = (hF * 60 + mF) - (hI * 60 + mI);
      return Math.floor(minutos / 50);
    } catch {
      return 0;
    }
  };

  const handleDelete = async () => {
    try {
      const cellData = scheduleData.celdas.find(
        (c) =>
          c.dia === getCellDia() &&
          c.hora_inicio === getCellHoraInicio()
      );

      if (!cellData) {
        toast.error('No se pudo encontrar la celda');
        return;
      }

      await axios.delete(
        `${API}/schedule/${scheduleId}/cell/${cellData.dia}/${cellData.hora_inicio}/block/${block.id}`
      );

      const updatedSchedule = { ...scheduleData };
      const cell = updatedSchedule.celdas.find(
        (c) => c.dia === cellData.dia && c.hora_inicio === cellData.hora_inicio
      );
      cell.bloques = cell.bloques.filter((b) => b.id !== block.id);

      setScheduleData(updatedSchedule);
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

  const totalBloques = horarios.reduce((sum, h) => sum + (h.bloques_cantidad || 0), 0);

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
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto" data-testid="edit-block-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between">
            <span>Editar Bloque</span>
            {getStatusBadge()}
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
              {horarios.length > 0 && (
                <Badge variant="secondary" className="ml-2 text-xs" data-testid="horarios-count-badge">
                  {horarios.length}
                </Badge>
              )}
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
                  placeholder="Buscar materia..."
                  data-testid="materia-input"
                />
                {searching && (
                  <div className="absolute right-3 top-3">
                    <Search className="w-4 h-4 animate-spin text-slate-400" />
                  </div>
                )}
                {showSuggestions && suggestions.length > 0 && (
                  <div className="absolute z-50 w-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-60 overflow-auto">
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
                placeholder="Ej: A1, B2"
                data-testid="grupo-input"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="docente">Docente</Label>
              <Input
                id="docente"
                value={formData.docente}
                onChange={(e) => handleChange('docente', e.target.value)}
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

          <TabsContent value="horarios" className="space-y-3 py-4" data-testid="horarios-tab-content">
            <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg border border-slate-200">
              <div>
                <p className="text-sm font-medium text-slate-900">Bloques de 50 minutos</p>
                <p className="text-xs text-slate-500">
                  {horarios.length} intervalo{horarios.length !== 1 ? 's' : ''} • {totalBloques} bloque{totalBloques !== 1 ? 's' : ''} de 50 min
                </p>
              </div>
              <Button
                size="sm"
                onClick={handleAddHorario}
                data-testid="add-horario-btn"
              >
                <Plus className="w-4 h-4 mr-1" />
                Agregar
              </Button>
            </div>

            {horarios.length === 0 ? (
              <div className="text-center py-8 border-2 border-dashed border-slate-200 rounded-lg">
                <Clock className="w-8 h-8 mx-auto text-slate-300 mb-2" />
                <p className="text-sm text-slate-500">No hay horarios definidos</p>
                <p className="text-xs text-slate-400 mt-1">
                  Agrega intervalos para definir cuándo se imparte la clase
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {horarios.map((horario, index) => (
                  <div
                    key={index}
                    className="p-3 border border-slate-200 rounded-lg space-y-2 bg-white"
                    data-testid={`horario-item-${index}`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-slate-600">
                        Intervalo #{index + 1}
                      </span>
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-xs">
                          {horario.bloques_cantidad || 0} × 50min
                        </Badge>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-7 w-7 text-red-500 hover:text-red-700 hover:bg-red-50"
                          onClick={() => handleRemoveHorario(index)}
                          data-testid={`remove-horario-${index}`}
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-2">
                      <div className="space-y-1">
                        <Label className="text-xs">Día</Label>
                        <Select
                          value={horario.dia}
                          onValueChange={(value) => handleUpdateHorario(index, 'dia', value)}
                        >
                          <SelectTrigger className="h-9" data-testid={`horario-dia-${index}`}>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {DIAS_OPCIONES.map((d) => (
                              <SelectItem key={d.value} value={d.value}>
                                {d.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="space-y-1">
                        <Label className="text-xs">Inicio</Label>
                        <Input
                          type="time"
                          value={horario.hora_inicio}
                          onChange={(e) => handleUpdateHorario(index, 'hora_inicio', e.target.value)}
                          className="h-9"
                          data-testid={`horario-inicio-${index}`}
                        />
                      </div>

                      <div className="space-y-1">
                        <Label className="text-xs">Fin</Label>
                        <Input
                          type="time"
                          value={horario.hora_fin}
                          onChange={(e) => handleUpdateHorario(index, 'hora_fin', e.target.value)}
                          className="h-9"
                          data-testid={`horario-fin-${index}`}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
              <p className="text-xs text-blue-800">
                <strong>Nota:</strong> Cada bloque equivale a 50 minutos. Por ejemplo, 8:40–10:20 corresponde a 2 bloques (100 min).
              </p>
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
