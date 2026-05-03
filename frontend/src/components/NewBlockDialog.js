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
import { toast } from 'sonner';
import { useSchedule } from '../context/ScheduleContext';
import { Search, Plus } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const NewBlockDialog = ({ cellSlot, onClose }) => {
  const { scheduleId } = useParams();
  const { scheduleData, setScheduleData } = useSchedule();
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
    setFormData((p) => ({ ...p, [field]: value }));
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
    try {
      await axios.post(`${API}/schedule/${scheduleId}/block`, {
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

      // Refrescar estado
      const fresh = await axios.get(`${API}/schedule/${scheduleId}`);
      const hoja = scheduleData.hoja_actual;
      const sheetData = fresh.data.hojas_data?.[hoja];
      setScheduleData({
        ...fresh.data,
        hoja_actual: hoja,
        celdas: sheetData?.celdas || fresh.data.celdas || [],
        estructura_dias: sheetData?.estructura_dias || fresh.data.estructura_dias || [],
        estructura_horas: sheetData?.estructura_horas || fresh.data.estructura_horas || [],
        excel_preview: sheetData?.excel_preview || fresh.data.excel_preview || [],
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
      <DialogContent className="sm:max-w-[500px]" data-testid="new-block-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Plus className="w-5 h-5" />
            Agregar materia en celda vacía
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
                placeholder="Buscar materia..."
                data-testid="nb-materia-input"
              />
              {searching && (
                <div className="absolute right-3 top-3">
                  <Search className="w-4 h-4 animate-spin text-slate-400" />
                </div>
              )}
              {showSuggestions && suggestions.length > 0 && (
                <div className="absolute z-50 w-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-60 overflow-auto">
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
