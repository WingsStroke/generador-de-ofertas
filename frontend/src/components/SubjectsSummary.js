import React, { useState, useMemo, useCallback } from 'react';
import { useSchedule } from '../context/ScheduleContext';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Badge } from './ui/badge';
import { RefreshCw, Search, User, MapPin, BookOpen, ChevronDown, ChevronUp, AlertTriangle } from 'lucide-react';

const SubjectsSummary = ({ onNavigate }) => {
  const { scheduleData } = useSchedule();
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const subjects = useMemo(() => {
    if (!scheduleData) return [];

    // Recopilar todos los bloques de todas las hojas
    const map = {};

    const processSheet = (sheetName, celdas) => {
      (celdas || []).forEach((celda) => {
        (celda.bloques || []).forEach((bloque) => {
          if (bloque._ghost) return;
          const key = bloque.materia_id || ('_nombre_' + (bloque.materia || '').toLowerCase().trim());
          if (!map[key]) {
            map[key] = {
              id: bloque.materia_id || key,
              nombre: bloque.materia || '(Sin nombre)',
              grupos: {},
            };
          }
          const grupoKey = (bloque.grupo || 'N/A') + '_' + (bloque.docente || '');
          if (!map[key].grupos[grupoKey]) {
            map[key].grupos[grupoKey] = {
              grupo: bloque.grupo || 'N/A',
              docente: bloque.docente || null,
              aula: bloque.aula || null,
              hoja: sheetName,
              dia: celda.dia,
              hora_inicio: celda.hora_inicio,
              bloque_id: bloque.id,
              horarios: [],
            };
          }
          map[key].grupos[grupoKey].horarios.push({
            dia: celda.dia,
            inicio: celda.hora_inicio,
            fin: celda.hora_fin,
          });
          // Actualizar aula/docente si aparece en algún bloque del grupo
          if (bloque.docente && !map[key].grupos[grupoKey].docente) {
            map[key].grupos[grupoKey].docente = bloque.docente;
          }
          if (bloque.aula && !map[key].grupos[grupoKey].aula) {
            map[key].grupos[grupoKey].aula = bloque.aula;
          }
        });
      });
    };

    if (scheduleData.hojas_data && Object.keys(scheduleData.hojas_data).length > 0) {
      Object.entries(scheduleData.hojas_data).forEach(([hoja, info]) => {
        processSheet(hoja, info.celdas);
      });
    } else {
      processSheet(scheduleData.hoja_actual || 'Tabla 1', scheduleData.celdas);
    }

    return Object.values(map)
      .map((s) => ({ ...s, grupos: Object.values(s.grupos) }))
      .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scheduleData, refreshKey]);

  const filtered = useMemo(() => {
    if (!search.trim()) return subjects;
    const q = search.toLowerCase().trim();
    return subjects.filter(
      (s) =>
        s.nombre.toLowerCase().includes(q) ||
        s.grupos.some(
          (g) =>
            (g.docente || '').toLowerCase().includes(q) ||
            (g.aula || '').toLowerCase().includes(q) ||
            (g.grupo || '').toLowerCase().includes(q)
        )
    );
  }, [subjects, search]);

  const hasWarning = useCallback((subject) => {
    return subject.grupos.some((g) => !g.docente || !g.aula);
  }, []);

  const DIA_LABELS = { L: 'Lun', M: 'Mar', W: 'Mié', J: 'Jue', V: 'Vie', S: 'Sáb' };

  return (
    <div className="flex flex-col h-full">
      {/* Encabezado */}
      <div className="px-4 py-3 border-b border-slate-200 bg-slate-50/50 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <BookOpen className="w-4 h-4 text-slate-500 shrink-0" />
          <span className="text-sm font-semibold text-slate-700 truncate">
            Resumen de asignaturas
          </span>
          <Badge variant="secondary" className="shrink-0">{subjects.length}</Badge>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setRefreshKey((k) => k + 1)}
          title="Actualizar lista"
          data-testid="refresh-subjects-btn"
        >
          <RefreshCw className="w-4 h-4" />
        </Button>
      </div>

      {/* Buscador */}
      <div className="px-3 py-2 border-b border-slate-100">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 w-3.5 h-3.5 text-slate-400" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar asignatura, docente o aula..."
            className="pl-8 h-8 text-xs"
          />
        </div>
      </div>

      {/* Lista */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 && (
          <div className="p-6 text-center text-sm text-slate-400">
            {search ? 'Sin resultados para la búsqueda.' : 'No hay asignaturas cargadas.'}
          </div>
        )}
        {filtered.map((subject) => {
          const isExpanded = expanded === subject.id;
          const warn = hasWarning(subject);
          return (
            <div key={subject.id} className="border-b border-slate-100 last:border-0">
              {/* Fila del nombre de asignatura */}
              <button
                className={`w-full text-left px-3 py-2 flex items-start justify-between gap-2 hover:bg-slate-50 transition-colors ${isExpanded ? 'bg-slate-50' : ''}`}
                onClick={() => setExpanded(isExpanded ? null : subject.id)}
                data-testid={`subject-row-${subject.id}`}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {warn && (
                      <AlertTriangle
                        className="w-3 h-3 text-amber-500 shrink-0"
                        title="Uno o más grupos sin docente o aula"
                      />
                    )}
                    <span className="text-xs font-semibold text-slate-800 leading-tight">
                      {subject.nombre}
                    </span>
                  </div>
                  <div className="text-[10px] text-slate-400 mt-0.5">
                    {subject.grupos.length} grupo{subject.grupos.length !== 1 ? 's' : ''}
                  </div>
                </div>
                <div className="shrink-0 text-slate-400 mt-0.5">
                  {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                </div>
              </button>

              {/* Detalle de grupos */}
              {isExpanded && (
                <div className="bg-white border-t border-slate-100 divide-y divide-slate-50">
                  {subject.grupos.map((grupo, i) => (
                    <div key={i} className="px-4 py-2 space-y-1">
                      <div className="flex items-center justify-between gap-2">
                        <Badge variant="outline" className="text-[10px] h-5">
                          Grupo {grupo.grupo}
                        </Badge>
                        <button
                          className="text-[10px] text-blue-600 hover:underline shrink-0"
                          onClick={() => onNavigate && onNavigate(grupo.hoja, grupo.dia, grupo.hora_inicio)}
                          title="Ir a la tabla"
                          data-testid={`go-to-block-${grupo.bloque_id}`}
                        >
                          Ver en tabla →
                        </button>
                      </div>

                      {grupo.docente ? (
                        <div className="flex items-center gap-1 text-[10px] text-blue-600">
                          <User className="w-3 h-3 shrink-0" />
                          <span>{grupo.docente}</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1 text-[10px] text-amber-500">
                          <User className="w-3 h-3 shrink-0" />
                          <span className="italic">Sin docente asignado</span>
                        </div>
                      )}

                      {grupo.aula ? (
                        <div className="flex items-center gap-1 text-[10px] text-emerald-600">
                          <MapPin className="w-3 h-3 shrink-0" />
                          <span>{grupo.aula}</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1 text-[10px] text-amber-500">
                          <MapPin className="w-3 h-3 shrink-0" />
                          <span className="italic">Sin aula asignada</span>
                        </div>
                      )}

                      <div className="flex flex-wrap gap-1 pt-0.5">
                        {grupo.horarios.map((h, j) => (
                          <span
                            key={j}
                            className="inline-flex items-center gap-0.5 text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded"
                          >
                            <span className="font-medium">{DIA_LABELS[h.dia] || h.dia}</span>
                            <span>{h.inicio}–{h.fin}</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default SubjectsSummary;
