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
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Badge } from './ui/badge';
import { toast } from 'sonner';
import { useSchedule } from '../context/ScheduleContext';
import { Search, Trash2 } from 'lucide-react';

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
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    const searchSubjects = async () => {
      if (formData.materia.length < 2) {
        setSuggestions([]);
        return;
      }

      setSearching(true);
      try {
        const response = await axios.get(
          `${API}/subjects/search/${encodeURIComponent(formData.materia)}`
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
  }, [formData.materia]);

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
      const cellData = scheduleData.celdas.find(
        (c) =>
          c.dia === getCellDia() &&
          c.hora_inicio === getCellHoraInicio()
      );

      if (!cellData) {
        toast.error('No se pudo encontrar la celda');
        return;
      }

      await axios.put(
        `${API}/schedule/${scheduleId}/cell/${cellData.dia}/${cellData.hora_inicio}/block/${block.id}`,
        formData
      );

      const updatedSchedule = { ...scheduleData };
      const cell = updatedSchedule.celdas.find(
        (c) => c.dia === cellData.dia && c.hora_inicio === cellData.hora_inicio
      );
      const blockIndex = cell.bloques.findIndex((b) => b.id === block.id);
      if (blockIndex !== -1) {
        cell.bloques[blockIndex] = {
          ...cell.bloques[blockIndex],
          ...formData,
          estado: 'confirmed',
          nivel_confianza: 1.0,
        };
      }

      setScheduleData(updatedSchedule);
      toast.success('Bloque actualizado exitosamente');
      onClose();
    } catch (error) {
      console.error('Error updating block:', error);
      toast.error('Error al actualizar el bloque');
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

  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[500px]" data-testid="edit-block-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between">
            <span>Editar Bloque</span>
            {getStatusBadge()}
          </DialogTitle>
          <DialogDescription>
            Edita la información del bloque de clase. Los cambios se guardarán con estado confirmado.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
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
        </div>

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
