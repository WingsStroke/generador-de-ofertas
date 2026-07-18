import React, { useState, useMemo, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useSchedule } from '../context/ScheduleContext';
import { useAuth } from '../context/AuthContext';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Input } from './ui/input';
import { toast } from 'sonner';
import {
  Users, BookOpen, Search, CheckCircle2, PlusCircle,
  Download, ChevronDown, ChevronUp, AlertCircle, ArrowRight, TableProperties
} from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = BACKEND_URL ? `${BACKEND_URL}/api` : '/api';

// ─── Extraer docentes con TODAS sus ubicaciones por hoja ─────────────────────
function extractTeachersFromSchedule(scheduleData) {
  if (!scheduleData) return [];
  // nombre → { nombre, maxConf, hojas: Map<sheetName, {hoja,dia,hora_inicio}> }
  const map = new Map();

  const processSheet = (sheetName, celdas) => {
    (celdas || []).forEach((celda) => {
      (celda.bloques || []).forEach((bloque) => {
        if (bloque._ghost) return;
        const nombre = (bloque.docente || '').trim();
        if (!nombre || nombre.toUpperCase() === 'N/A') return;
        const conf = bloque.nivel_confianza ?? 1;

        if (!map.has(nombre)) {
          map.set(nombre, { nombre, maxConf: conf, hojas: new Map() });
        }
        const entry = map.get(nombre);
        if (conf > entry.maxConf) entry.maxConf = conf;

        // Guardar solo la primera ocurrencia de este docente en esta hoja
        if (!entry.hojas.has(sheetName)) {
          entry.hojas.set(sheetName, {
            hoja: sheetName,
            dia: celda.dia,
            hora_inicio: celda.hora_inicio,
          });
        }
      });
    });
  };

  if (scheduleData.hojas_data && Object.keys(scheduleData.hojas_data).length > 0) {
    Object.entries(scheduleData.hojas_data).forEach(([hoja, info]) =>
      processSheet(hoja, info.celdas)
    );
  } else {
    processSheet(scheduleData.hoja_actual || 'Tabla 1', scheduleData.celdas);
  }

  return Array.from(map.values())
    .map((t) => ({ ...t, hojas: Array.from(t.hojas.values()) }))
    .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'));
}

// ─── Extraer asignaturas con su primera ubicación ────────────────────────────
function extractSubjectsFromSchedule(scheduleData) {
  if (!scheduleData) return [];
  const map = {};

  const processSheet = (sheetName, celdas) => {
    (celdas || []).forEach((celda) => {
      (celda.bloques || []).forEach((bloque) => {
        if (bloque._ghost) return;
        const key = bloque.materia_id || ('_' + (bloque.materia || '').toLowerCase().trim());
        if (!map[key]) {
          map[key] = {
            id: bloque.materia_id || key,
            nombre: bloque.materia || '(Sin nombre)',
            confianzas: [],
            hoja: sheetName,
            dia: celda.dia,
            hora_inicio: celda.hora_inicio,
          };
        }
        map[key].confianzas.push(bloque.nivel_confianza ?? 0);
      });
    });
  };

  if (scheduleData.hojas_data && Object.keys(scheduleData.hojas_data).length > 0) {
    Object.entries(scheduleData.hojas_data).forEach(([hoja, info]) =>
      processSheet(hoja, info.celdas)
    );
  } else {
    processSheet(scheduleData.hoja_actual || 'Tabla 1', scheduleData.celdas);
  }

  return Object.values(map)
    .map((s) => ({
      ...s,
      avgConf: s.confianzas.reduce((a, b) => a + b, 0) / (s.confianzas.length || 1),
    }))
    .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'));
}

// ─── Indicador de confianza ──────────────────────────────────────────────────
const ConfidencePill = ({ conf, inDict }) => {
  if (inDict) return (
    <span className="inline-flex items-center gap-1 text-[10px] bg-emerald-50 text-emerald-700 border border-emerald-200 px-1.5 py-0.5 rounded-full font-medium">
      <CheckCircle2 className="w-3 h-3" /> En diccionario
    </span>
  );
  if (conf >= 0.85) return (
    <span className="inline-flex items-center gap-1 text-[10px] bg-blue-50 text-blue-700 border border-blue-200 px-1.5 py-0.5 rounded-full font-medium">
      <CheckCircle2 className="w-3 h-3" /> Alta confianza
    </span>
  );
  if (conf >= 0.5) return (
    <span className="inline-flex items-center gap-1 text-[10px] bg-amber-50 text-amber-700 border border-amber-200 px-1.5 py-0.5 rounded-full font-medium">
      <AlertCircle className="w-3 h-3" /> Inferido
    </span>
  );
  return (
    <span className="inline-flex items-center gap-1 text-[10px] bg-red-50 text-red-700 border border-red-200 px-1.5 py-0.5 rounded-full font-medium">
      <AlertCircle className="w-3 h-3" /> Dudoso
    </span>
  );
};

// ─── Componente principal ────────────────────────────────────────────────────
const DictionaryPanel = ({ scheduleId, onNavigate }) => {
  const { scheduleData } = useSchedule();
  const { role } = useAuth();
  const [activeTab, setActiveTab] = useState('docentes');
  const [knownTeachers, setKnownTeachers] = useState(new Set());
  const [loadingDict, setLoadingDict] = useState(false);
  const [saving, setSaving] = useState(false);
  const [searchDoc, setSearchDoc] = useState('');
  const [searchAsig, setSearchAsig] = useState('');
  const [expandedTeacher, setExpandedTeacher] = useState(null);
  const [expandedSubject, setExpandedSubject] = useState(null);
  const [subjectsSummary, setSubjectsSummary] = useState([]);
  const [subjectsLoading, setSubjectsLoading] = useState(false);
  const [subjectEdits, setSubjectEdits] = useState({});
  const [savingSubjectId, setSavingSubjectId] = useState(null);

  const fetchDict = useCallback(async () => {
    setLoadingDict(true);
    try {
      const res = await axios.get(`${API}/teachers?t=${Date.now()}`);
      setKnownTeachers(new Set((res.data.teachers || []).map((t) => t.toUpperCase())));
    } catch { /* silencioso */ }
    finally { setLoadingDict(false); }
  }, []);

  useEffect(() => { fetchDict(); }, [fetchDict]);

  const fetchSubjectsSummary = useCallback(async () => {
    if (!scheduleId) return;
    setSubjectsLoading(true);
    try {
      const res = await axios.get(`${API}/schedule/${scheduleId}/subjects-summary`);
      setSubjectsSummary(res.data.subjects || []);
    } catch (error) {
      console.error('Error cargando resumen de asignaturas:', error);
      setSubjectsSummary([]);
    } finally {
      setSubjectsLoading(false);
    }
  }, [scheduleId]);

  useEffect(() => {
    fetchSubjectsSummary();
  }, [fetchSubjectsSummary, scheduleData]);

  const teachers = useMemo(() => extractTeachersFromSchedule(scheduleData), [scheduleData]);
  const subjects = useMemo(() => subjectsSummary, [subjectsSummary]);

  const newTeachers = useMemo(
    () => teachers.filter((t) => !knownTeachers.has(t.nombre.toUpperCase())),
    [teachers, knownTeachers]
  );

  const filteredTeachers = useMemo(() => {
    const q = searchDoc.toLowerCase().trim();
    return q ? teachers.filter((t) => t.nombre.toLowerCase().includes(q)) : teachers;
  }, [teachers, searchDoc]);

  const filteredSubjects = useMemo(() => {
    const q = searchAsig.toLowerCase().trim();
    return q ? subjects.filter((s) => s.nombre.toLowerCase().includes(q)) : subjects;
  }, [subjects, searchAsig]);

  const handleSubjectEditChange = (subjectId, field, value) => {
    setSubjectEdits((prev) => ({
      ...prev,
      [subjectId]: {
        ...(prev[subjectId] || {}),
        [field]: value,
      },
    }));
  };

  const getSubjectDraft = (subject) => {
    const draft = subjectEdits[subject.id] || {};
    return {
      codigo: draft.codigo !== undefined ? draft.codigo : (subject.codigo || ''),
      creditos: draft.creditos !== undefined ? draft.creditos : (subject.creditos ?? ''),
    };
  };

  const handleUpdateSubjectMetadata = async (subject) => {
    if (role !== 'admin') return;
    const draft = getSubjectDraft(subject);
    setSavingSubjectId(subject.id);
    try {
      await axios.patch(`${API}/schedule/${scheduleId}/subject/${encodeURIComponent(subject.id)}/metadata`, {
        codigo: draft.codigo || null,
        creditos: draft.creditos === '' ? null : Number(draft.creditos),
      });
      toast.success('Metadatos de asignatura actualizados en el horario');
      await fetchSubjectsSummary();
    } catch (error) {
      const detail = error?.response?.data?.detail || 'No se pudieron actualizar los metadatos';
      toast.error(detail);
    } finally {
      setSavingSubjectId(null);
    }
  };

  const handleSaveSubjectGlobal = async (subject) => {
    if (role !== 'admin') return;
    const draft = getSubjectDraft(subject);
    setSavingSubjectId(subject.id);
    try {
      await axios.post(`${API}/schedule/${scheduleId}/subject/${encodeURIComponent(subject.id)}/save-global`, {
        codigo: draft.codigo || null,
        creditos: draft.creditos === '' ? null : Number(draft.creditos),
      });
      toast.success('Asignatura guardada en diccionario global');
      await fetchSubjectsSummary();
    } catch (error) {
      const detail = error?.response?.data?.detail || 'No se pudo guardar la asignatura global';
      toast.error(detail);
    } finally {
      setSavingSubjectId(null);
    }
  };

  const handleSaveNew = async () => {
    if (newTeachers.length === 0) { toast.info('Todos los docentes ya están en el diccionario.'); return; }
    setSaving(true);
    try {
      const res = await axios.post(`${API}/teachers/extract-from-schedule/${scheduleId}`);
      toast[res.data.added > 0 ? 'success' : 'info'](
        res.data.added > 0 ? res.data.message : 'Todos los docentes ya estaban en el diccionario.'
      );
      await fetchDict();
    } catch { toast.error('Error al guardar docentes en el diccionario.'); }
    finally { setSaving(false); }
  };

  const handleGoTo = (hoja, dia, hora_inicio) => {
    if (onNavigate) onNavigate(hoja, dia, hora_inicio);
  };

  return (
    <div className="flex flex-col h-full">

      {/* ── Tabs ─────────────────────────────────────────────────────────── */}
      <div className="flex border-b border-slate-200 bg-slate-50/50">
        {[
          { key: 'docentes', label: 'Docentes', icon: Users, count: teachers.length, alert: newTeachers.length > 0 },
          { key: 'asignaturas', label: 'Asignaturas', icon: BookOpen, count: subjects.length, alert: false },
        ].map(({ key, label, icon: Icon, count, alert }) => (
          <button
            key={key}
            className={`flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-semibold transition-colors
              ${activeTab === key ? 'border-b-2 border-blue-600 text-blue-700 bg-white' : 'text-slate-500 hover:text-slate-700'}`}
            onClick={() => setActiveTab(key)}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
            <Badge variant="secondary" className={`text-[10px] h-4 px-1.5 ${alert ? 'bg-amber-100 text-amber-700' : ''}`}>
              {count}
            </Badge>
          </button>
        ))}
      </div>

      {/* ── DOCENTES ─────────────────────────────────────────────────────── */}
      {activeTab === 'docentes' && (
        <div className="flex flex-col flex-1 overflow-hidden">
          {/* Barra de acciones */}
          <div className="px-3 py-2 border-b border-slate-100 bg-white space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] text-slate-500">
                {newTeachers.length > 0
                  ? <span className="text-amber-600 font-medium">{newTeachers.length} nuevo{newTeachers.length !== 1 ? 's' : ''}</span>
                  : <span className="text-emerald-600 font-medium">Todos en diccionario ✓</span>}
              </span>
              {role === 'admin' && (
                <Button
                  size="sm"
                  className="h-7 text-[11px] bg-blue-600 hover:bg-blue-700 text-white gap-1"
                  onClick={handleSaveNew}
                  disabled={saving || loadingDict || newTeachers.length === 0}
                >
                  {saving
                    ? <span className="animate-pulse">Guardando...</span>
                    : <><Download className="w-3 h-3" />Guardar nuevos</>}
                </Button>
              )}
            </div>
            <div className="relative">
              <Search className="absolute left-2.5 top-2 w-3.5 h-3.5 text-slate-400" />
              <Input value={searchDoc} onChange={(e) => setSearchDoc(e.target.value)}
                placeholder="Buscar docente..." className="pl-8 h-7 text-xs" />
            </div>
          </div>

          {/* Lista expandible */}
          <div className="flex-1 overflow-y-auto">
            {filteredTeachers.length === 0 && (
              <div className="p-6 text-center text-xs text-slate-400">
                {searchDoc ? 'Sin resultados.' : 'No se encontraron docentes en el horario.'}
              </div>
            )}
            {filteredTeachers.map((t) => {
              const inDict = knownTeachers.has(t.nombre.toUpperCase());
              const isExpanded = expandedTeacher === t.nombre;
              return (
                <div key={t.nombre} className={`border-b border-slate-100 last:border-0 ${inDict ? '' : 'bg-amber-50/30'}`}>
                  {/* Cabecera del docente */}
                  <button
                    className={`w-full text-left px-3 py-2.5 flex items-center justify-between gap-2 hover:bg-slate-50 transition-colors ${isExpanded ? 'bg-slate-50' : ''}`}
                    onClick={() => setExpandedTeacher(isExpanded ? null : t.nombre)}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      {inDict
                        ? <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                        : <PlusCircle className="w-4 h-4 text-amber-500 shrink-0" />}
                      <div className="min-w-0">
                        <span className="text-xs font-medium text-slate-700 block truncate">{t.nombre}</span>
                        <span className="text-[10px] text-slate-400">
                          {t.hojas.length} tabla{t.hojas.length !== 1 ? 's' : ''}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${inDict ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
                        {inDict ? 'Conocido' : 'Nuevo'}
                      </span>
                      {isExpanded ? <ChevronUp className="w-3.5 h-3.5 text-slate-400" /> : <ChevronDown className="w-3.5 h-3.5 text-slate-400" />}
                    </div>
                  </button>

                  {/* Detalle: tablas donde aparece */}
                  {isExpanded && (
                    <div className="bg-white border-t border-slate-100 px-4 py-2.5 space-y-1.5">
                      <p className="text-[10px] text-slate-400 font-medium uppercase tracking-wide mb-2">
                        Presente en:
                      </p>
                      {t.hojas.map((loc) => (
                        <button
                          key={loc.hoja}
                          className="w-full flex items-center justify-between gap-2 text-[11px] text-blue-600 hover:text-blue-800 font-medium bg-blue-50 hover:bg-blue-100 rounded-md px-3 py-1.5 transition-colors"
                          onClick={() => handleGoTo(loc.hoja, loc.dia, loc.hora_inicio)}
                          title={`Ir a ${loc.hoja}`}
                        >
                          <span className="flex items-center gap-1.5">
                            <TableProperties className="w-3.5 h-3.5 shrink-0" />
                            {loc.hoja}
                          </span>
                          <ArrowRight className="w-3.5 h-3.5 shrink-0" />
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── ASIGNATURAS ──────────────────────────────────────────────────── */}
      {activeTab === 'asignaturas' && (
        <div className="flex flex-col flex-1 overflow-hidden">
          <div className="px-3 py-2 border-b border-slate-100 bg-white space-y-2">
            <p className="text-[10px] text-slate-500">
              Metadatos por asignatura: ID, código, créditos, confianza y fuente.
            </p>
            <div className="relative">
              <Search className="absolute left-2.5 top-2 w-3.5 h-3.5 text-slate-400" />
              <Input value={searchAsig} onChange={(e) => setSearchAsig(e.target.value)}
                placeholder="Buscar asignatura..." className="pl-8 h-7 text-xs" />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {subjectsLoading && (
              <div className="p-4 text-center text-xs text-slate-500">Cargando asignaturas...</div>
            )}
            {filteredSubjects.length === 0 && (
              <div className="p-6 text-center text-xs text-slate-400">
                {searchAsig ? 'Sin resultados.' : 'No hay asignaturas en el horario.'}
              </div>
            )}
            {filteredSubjects.map((s) => {
              const isExpanded = expandedSubject === s.id;
              const conf = s.confianza_promedio ?? 0;
              const draft = getSubjectDraft(s);
              const isBase = !!s.is_base;
              const isSaving = savingSubjectId === s.id;
              return (
                <div key={s.id} className="border-b border-slate-100 last:border-0">
                  <button
                    className={`w-full text-left px-3 py-2.5 flex items-start justify-between gap-2 hover:bg-slate-50 transition-colors ${isExpanded ? 'bg-slate-50' : ''}`}
                    onClick={() => setExpandedSubject(isExpanded ? null : s.id)}
                  >
                    <div className="min-w-0 flex-1 space-y-1">
                      <span className="text-xs font-semibold text-slate-800 block truncate">{s.nombre}</span>
                      <div className="flex items-center gap-2">
                        <ConfidencePill conf={conf} inDict={s.source === 'base' || s.source === 'global'} />
                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                          s.source === 'base'
                            ? 'bg-emerald-50 text-emerald-700'
                            : s.source === 'global'
                              ? 'bg-blue-50 text-blue-700'
                              : 'bg-amber-50 text-amber-700'
                        }`}>
                          {s.source === 'base' ? 'Base' : s.source === 'global' ? 'Global' : 'Manual'}
                        </span>
                      </div>
                    </div>
                    <span className="text-slate-400 mt-0.5 shrink-0">
                      {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </span>
                  </button>

                  {isExpanded && (
                    <div className="bg-white border-t border-slate-100 px-4 py-2.5 space-y-2">
                      <div className="space-y-1 text-[11px] text-slate-600">
                        <div className="flex justify-between">
                          <span className="text-slate-400">ID materia</span>
                          <span className="font-mono font-medium text-slate-700">{s.id}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-400">Confianza promedio</span>
                          <span className={`font-medium ${conf >= 0.85 ? 'text-blue-600' : conf >= 0.5 ? 'text-amber-600' : 'text-red-500'}`}>
                            {(conf * 100).toFixed(0)}%
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-400">Ocurrencias</span>
                          <span className="font-medium">{s.ocurrencias}</span>
                        </div>
                        <div className="grid grid-cols-2 gap-2 pt-1">
                          <div className="space-y-1">
                            <span className="text-slate-400 text-[10px]">Código</span>
                            <Input
                              value={draft.codigo}
                              onChange={(e) => handleSubjectEditChange(s.id, 'codigo', e.target.value)}
                              className="h-7 text-xs"
                              placeholder="Ej: MAT101"
                              disabled={role !== 'admin' || isBase || isSaving}
                            />
                          </div>
                          <div className="space-y-1">
                            <span className="text-slate-400 text-[10px]">Créditos</span>
                            <Input
                              value={draft.creditos}
                              onChange={(e) => handleSubjectEditChange(s.id, 'creditos', e.target.value)}
                              className="h-7 text-xs"
                              placeholder="Ej: 3"
                              disabled={role !== 'admin' || isBase || isSaving}
                            />
                          </div>
                        </div>
                      </div>
                      {role === 'admin' && (
                        <div className="flex items-center gap-2 pt-1">
                          <Button
                            size="sm"
                            className="h-7 text-[11px]"
                            disabled={isBase || isSaving}
                            onClick={() => handleUpdateSubjectMetadata(s)}
                          >
                            {isSaving ? 'Guardando...' : 'Guardar metadatos'}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 text-[11px]"
                            disabled={isBase || isSaving}
                            onClick={() => handleSaveSubjectGlobal(s)}
                          >
                            Guardar en global
                          </Button>
                          {isBase && (
                            <span className="text-[10px] text-slate-500">Asignatura base bloqueada</span>
                          )}
                        </div>
                      )}
                      {s.hoja && (
                        <button
                          className="w-full flex items-center justify-center gap-1.5 text-[11px] text-blue-600 hover:text-blue-800 font-medium bg-blue-50 hover:bg-blue-100 rounded-md py-1.5 transition-colors"
                          onClick={() => handleGoTo(s.hoja, s.dia, s.hora_inicio)}
                        >
                          Ver en tabla <ArrowRight className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

export default DictionaryPanel;
