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
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { toast } from 'sonner';
import { useSchedule } from '../context/ScheduleContext';
import { useHistory } from '../context/HistoryContext';
import { Search, Plus, Sparkles } from 'lucide-react';

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

const NewBlockDialog = ({ cellSlot, onClose }) => {
  const { scheduleId } = useParams();
  const { scheduleData, setScheduleData } = useSchedule();
  const { pushAction } = useHistory();
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
      } catch (e) {
        console.error(e);
      } finally {
        setSearching(false);
      }
    };
    const t = setTimeout(searchSubjects, 300);
    return () => clearTimeout(t);
  }, [formData.materia, scheduleData]);

  const handleChange = (field, value) => {
    setFormData((p) => {
      if (field === 'materia') {
        return { ...p, materia: value, materia_id: '' };
      }
      return { ...p, [field]: value };
    });
    if (field === 'materia') setShowSuggestions(true);
  };

  const pickSuggestion = (s) => {
    setFormData((p) => ({ ...p, materia: s.nombre, materia_id: s.id }));
    setShowSuggestions(false);
  };

  const handleSave = async () => {
    if (!formData.materia.trim()) {
      toast.error('La materia es obligatoria');
      return;
    }
    setSaving(true);
    
    // Guardar estado anterior para undo
    const previousSchedule = JSON.parse(JSON.stringify(scheduleData));
    
    try {
      const response = await axios.post(`${API}/schedule/${scheduleId}/block`, {
        sheet: scheduleData.hoja_actual,
        dia: cellSlot.dia,
        hora_inicio: cellSlot.hora_inicio,
        hora_fin: cellSlot.hora_fin,
        materia: formData.materia.trim(),
        materia_id: formData.materia_id || null,
        grupo: formData.grupo.trim() || null,
        docente: formData.docente.trim() || null,
        aula: formData.aula.trim() || null,
      });

      const newBlock = response.data.block;

      // Aplicar mutación local directa para no depender del refetch, igual que BlockEditor
      const updatedSchedule = JSON.parse(JSON.stringify(scheduleData));
      const hoja = updatedSchedule.hoja_actual;
      
      const applyNewBlock = (celdasList) => {
        if (!celdasList) return;
        let cell = celdasList.find(
          (c) => c.dia === cellSlot.dia && c.hora_inicio === cellSlot.hora_inicio
        );
        if (cell) {
          cell.bloques = cell.bloques || [];
          cell.bloques.push(newBlock);
        } else {
          celdasList.push({
            dia: cellSlot.dia,
            hora_inicio: cellSlot.hora_inicio,
            hora_fin: cellSlot.hora_fin,
            bloques: [newBlock],
            celda_ref: null,
          });
        }
      };

      // Actualizar celdas top-level
      applyNewBlock(updatedSchedule.celdas);
      
      // Actualizar en hojas_data
      if (updatedSchedule.hojas_data && hoja && updatedSchedule.hojas_data[hoja]) {
        applyNewBlock(updatedSchedule.hojas_data[hoja].celdas);
      }

      setScheduleData(updatedSchedule);

      // Registrar en historial
      pushAction({
        type: 'CREATE_BLOCK',
        description: `Crear bloque: ${formData.materia}`,
        payload: {
          blockId: newBlock.id,
          cellSlot,
          materia: formData.materia,
        },
        onUndo: () => {
          setScheduleData(previousSchedule);
          axios.put(`${API}/schedule/${scheduleId}/state`, previousSchedule).catch(console.error);
        },
        onRedo: () => {
          setScheduleData(updatedSchedule);
          axios.put(`${API}/schedule/${scheduleId}/state`, updatedSchedule).catch(console.error);
        },
      });

      toast.success('Materia agregada');
      onClose();
    } catch (e) {
      console.error(e);
      toast.error('No se pudo crear el bloque');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent 
        className="sm:max-w-[500px]" 
        data-testid="new-block-dialog"
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !showSuggestions && formData.materia.trim()) {
            e.preventDefault();
            handleSave();
          }
        }}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between w-full">
            <span className="flex items-center gap-2">
              <Plus className="w-5 h-5" />
              Agregar materia en celda vacía
            </span>
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
              title="Limpiar ruido de todos los campos"
            >
              <Sparkles className="w-3.5 h-3.5 mr-1" />
              Limpiar ruido
            </Button>
          </DialogTitle>
          <DialogDescription>
            {cellSlot.dia} · {cellSlot.hora_inicio}–{cellSlot.hora_fin} · {scheduleData?.hoja_actual}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="nb-materia">Materia *</Label>
            <div className="relative">
              <Input
                id="nb-materia"
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
                data-testid="nb-materia-input"
              />
              {searching && (
                <div className="absolute right-3 top-3">
                  <Search className="w-4 h-4 animate-spin text-slate-400" />
                </div>
              )}
              {showSuggestions && suggestions.length > 0 && (
                <div ref={suggestionsRef} className="absolute z-50 w-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-60 overflow-auto">
                  {suggestions.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      className="w-full text-left px-3 py-2 hover:bg-slate-50 transition-colors text-sm"
                      onClick={() => pickSuggestion(s)}
                      data-testid={`nb-suggestion-${s.id}`}
                    >
                      <div className="font-medium text-slate-900">{s.nombre}</div>
                      <div className="text-xs text-slate-500">
                        {s.codigo && `${s.codigo} • `}
                        {s.creditos != null && `${s.creditos} cr • `}
                        Confianza: {(s.confidence * 100).toFixed(0)}%
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="nb-grupo">Grupo</Label>
              <Input
                id="nb-grupo"
                value={formData.grupo}
                onChange={(e) => handleChange('grupo', e.target.value)}
                onBlur={(e) => {
                  const cleaned = cleanNoise(e.target.value);
                  if (cleaned !== e.target.value) {
                    handleChange('grupo', cleaned);
                  }
                }}
                placeholder="Ej: A1"
                data-testid="nb-grupo-input"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="nb-docente">Docente</Label>
              <Input
                id="nb-docente"
                value={formData.docente}
                onChange={(e) => handleChange('docente', e.target.value)}
                onBlur={(e) => {
                  const cleaned = cleanNoise(e.target.value);
                  if (cleaned !== e.target.value) {
                    handleChange('docente', cleaned);
                  }
                }}
                placeholder="Nombre del docente"
                data-testid="nb-docente-input"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="nb-aula">Aula</Label>
            <Input
              id="nb-aula"
              value={formData.aula}
              onChange={(e) => handleChange('aula', e.target.value)}
              onBlur={(e) => {
                const cleaned = cleanNoise(e.target.value);
                if (cleaned !== e.target.value) {
                  handleChange('aula', cleaned);
                }
              }}
              placeholder="Laboratorio, salón, etc."
              data-testid="nb-aula-input"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>Cancelar</Button>
          <Button onClick={handleSave} disabled={saving || !formData.materia.trim()} data-testid="nb-save-btn">
            {saving ? 'Guardando...' : 'Agregar materia'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default NewBlockDialog;
