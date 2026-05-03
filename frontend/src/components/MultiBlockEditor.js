import React, { useState, useEffect, useMemo } from 'react';
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
import { ScrollArea } from './ui/scroll-area';
import { toast } from 'sonner';
import { useSchedule } from '../context/ScheduleContext';
import { Search, X } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const MultiBlockEditor = ({ onClose }) => {
  const { scheduleId } = useParams();
  const {
    scheduleData,
    setScheduleData,
    selectedBlockIds,
    toggleBlockSelection,
    exitSelectionMode,
  } = useSchedule();

  const [formData, setFormData] = useState({
    materia: '',
    materia_id: '',
    grupo: '',
    docente: '',
    aula: '',
  });
  const [suggestions, setSuggestions] = useState([]);
  const [searching, setSearching] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [saving, setSaving] = useState(false);

  const selectedBlocks = useMemo(() => {
    if (!scheduleData) return [];
    const collections = [];
    if (scheduleData.hojas_data) {
      Object.entries(scheduleData.hojas_data).forEach(([hoja, info]) => {
        (info?.celdas || []).forEach((c) => {
          (c.bloques || []).forEach((b) => {
            if (selectedBlockIds.has(b.id)) {
              collections.push({ ...b, hoja, dia: c.dia, hora: c.hora_inicio });
            }
          });
        });
      });
    }
    if (collections.length === 0 && scheduleData.celdas) {
      scheduleData.celdas.forEach((c) => {
        (c.bloques || []).forEach((b) => {
          if (selectedBlockIds.has(b.id)) {
            collections.push({ ...b, hoja: scheduleData.hoja_actual, dia: c.dia, hora: c.hora_inicio });
          }
        });
      });
    }
    return collections;
  }, [scheduleData, selectedBlockIds]);

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
    if (field === 'materia') setShowSuggestions(true);
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
    if (selectedBlocks.length === 0) {
      toast.error('No hay bloques seleccionados');
      return;
    }
    const update = {};
    if (formData.materia.trim()) update.materia = formData.materia.trim();
    if (formData.materia_id.trim()) update.materia_id = formData.materia_id.trim();
    if (formData.grupo.trim()) update.grupo = formData.grupo.trim();
    if (formData.docente.trim()) update.docente = formData.docente.trim();
    if (formData.aula.trim()) update.aula = formData.aula.trim();

    if (Object.keys(update).length === 0) {
      toast.error('Indica al menos un campo a actualizar');
      return;
    }

    setSaving(true);
    try {
      const block_ids = Array.from(selectedBlockIds);
      const res = await axios.patch(
        `${API}/schedule/${scheduleId}/blocks/bulk`,
        { block_ids, update }
      );

      // Refrescar schedule completo para mantener todas las hojas sincronizadas
      const fresh = await axios.get(`${API}/schedule/${scheduleId}`);
      const currentSheet = scheduleData?.hoja_actual;
      const sheetData = fresh.data.hojas_data?.[currentSheet];
      setScheduleData({
        ...fresh.data,
        hoja_actual: currentSheet,
        celdas: sheetData?.celdas || fresh.data.celdas || [],
        estructura_dias: sheetData?.estructura_dias || fresh.data.estructura_dias || [],
        estructura_horas: sheetData?.estructura_horas || fresh.data.estructura_horas || [],
        excel_preview: sheetData?.excel_preview || fresh.data.excel_preview || [],
      });

      toast.success(`${res.data.updated.length} bloque(s) actualizado(s)`);
      exitSelectionMode();
      onClose();
    } catch (error) {
      console.error('Error bulk update:', error);
      toast.error('Error al actualizar los bloques');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[640px] max-h-[90vh] overflow-y-auto" data-testid="multi-edit-dialog">
        <DialogHeader>
          <DialogTitle>
            Edición múltiple ({selectedBlocks.length} bloque{selectedBlocks.length !== 1 ? 's' : ''})
          </DialogTitle>
          <DialogDescription>
            Solo se aplicarán los campos que rellenes. Los campos vacíos quedan intactos en cada bloque.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="border border-slate-200 rounded-lg">
            <div className="px-3 py-2 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-700">Bloques seleccionados</span>
              <Badge variant="secondary" data-testid="multi-edit-count">{selectedBlocks.length}</Badge>
            </div>
            <ScrollArea className="max-h-40">
              <div className="p-2 space-y-1">
                {selectedBlocks.map((b) => (
                  <div
                    key={b.id}
                    className="flex items-center justify-between text-xs px-2 py-1 rounded hover:bg-slate-50"
                    data-testid={`multi-edit-item-${b.id}`}
                  >
                    <div className="truncate">
                      <span className="font-medium text-slate-800">{b.materia || '(sin materia)'}</span>
                      <span className="text-slate-500 ml-2">
                        {b.hoja} · {b.dia} {b.hora}
                        {b.grupo ? ` · (${b.grupo})` : ''}
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => toggleBlockSelection(b.id)}
                      className="text-slate-400 hover:text-red-500 transition-colors ml-2"
                      data-testid={`multi-edit-remove-${b.id}`}
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </div>

          <div className="space-y-2">
            <Label htmlFor="me-materia">Materia (opcional)</Label>
            <div className="relative">
              <Input
                id="me-materia"
                value={formData.materia}
                onChange={(e) => handleChange('materia', e.target.value)}
                placeholder="Buscar materia..."
                data-testid="multi-materia-input"
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
                      data-testid={`multi-suggestion-${subject.id}`}
                    >
                      <div className="font-medium text-slate-900">{subject.nombre}</div>
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

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="me-grupo">Grupo (opcional)</Label>
              <Input
                id="me-grupo"
                value={formData.grupo}
                onChange={(e) => handleChange('grupo', e.target.value)}
                placeholder="Ej: A1, B2"
                data-testid="multi-grupo-input"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="me-docente">Docente (opcional)</Label>
              <Input
                id="me-docente"
                value={formData.docente}
                onChange={(e) => handleChange('docente', e.target.value)}
                placeholder="Nombre del docente"
                data-testid="multi-docente-input"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="me-aula">Aula (opcional)</Label>
            <Input
              id="me-aula"
              value={formData.aula}
              onChange={(e) => handleChange('aula', e.target.value)}
              placeholder="Laboratorio, salón, etc."
              data-testid="multi-aula-input"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancelar
          </Button>
          <Button
            onClick={handleSave}
            disabled={saving || selectedBlocks.length === 0}
            data-testid="multi-save-btn"
          >
            {saving ? 'Guardando...' : `Aplicar a ${selectedBlocks.length} bloque(s)`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default MultiBlockEditor;
