import React, { useState } from 'react';
import { DragDropContext, Droppable, Draggable } from '@hello-pangea/dnd';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { useSchedule } from '../context/ScheduleContext';
import { useHistory } from '../context/HistoryContext';
import { useCollab } from '../context/CollabContext';
import BlockEditor from './BlockEditor';
import MultiBlockEditor from './MultiBlockEditor';
import NewBlockDialog from './NewBlockDialog';
import { Check, Plus } from 'lucide-react';
import { toast } from 'sonner';
import '@/App.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = BACKEND_URL ? `${BACKEND_URL}/api` : '/api';

const ScheduleGrid = () => {
  const { scheduleId } = useParams();
  const {
    scheduleData,
    setScheduleData,
    selectedCell,
    setSelectedCell,
    selectionMode,
    selectedBlockIds,
    toggleBlockSelection,
  } = useSchedule();
  const { pushAction } = useHistory();
  const [editingBlock, setEditingBlock] = useState(null);
  const [showMultiEditor, setShowMultiEditor] = useState(false);
  const [newBlockSlot, setNewBlockSlot] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [expandedCells, setExpandedCells] = useState(new Set());
  const { isSheetLockedByOther, locks } = useCollab();

  if (!scheduleData) return null;

  const currentSheet = scheduleData.hoja_actual;
  const isLocked = currentSheet ? isSheetLockedByOther(currentSheet) : false;

  const { estructura_dias, estructura_horas, celdas } = scheduleData;

  const getCellData = (dia, hora_inicio) => {
    return celdas.find(
      (c) => c.dia === dia && c.hora_inicio === hora_inicio
    );
  };

  const getCellId = (dia, hora_inicio) => `${dia}-${hora_inicio}`;

  const handleCellClick = (dia, hora_inicio, celda_ref) => {
    if (!isDragging) {
      setSelectedCell({ dia, hora_inicio, celda_ref });
    }
  };

  const handleBlockClick = (block, e, dia, hora_inicio, celda_ref) => {
    e.stopPropagation();
    if (isDragging) return;

    // Si se presiona Ctrl, Alt o Shift al hacer clic, se ilumina la celda en ambas tablas
    if (e.ctrlKey || e.altKey || e.shiftKey) {
      setSelectedCell({ dia, hora_inicio, celda_ref });
      return;
    }

    if (isLocked) {
      toast.error(`La hoja está bloqueada por ${locks[currentSheet]}`);
      return;
    }

    if (selectionMode) {
      if (block._ghost) return; // Ghosts no participan en selección múltiple
      toggleBlockSelection(block.id);
    } else {
      setEditingBlock(block);
    }
  };

  const toggleCellExpansion = (cellId, e) => {
    e.stopPropagation();
    setExpandedCells((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(cellId)) {
        newSet.delete(cellId);
      } else {
        newSet.add(cellId);
      }
      return newSet;
    });
  };

  const isCellExpanded = (cellId) => expandedCells.has(cellId);

  const onDragStart = () => {
    if (isLocked) {
      toast.error(`La hoja está bloqueada por ${locks[currentSheet]}`);
      return;
    }
    setIsDragging(true);
  };

  const onDragEnd = async (result) => {
    setIsDragging(false);

    if (!result.destination) {
      return;
    }

    const sourceId = result.source.droppableId;
    const destId = result.destination.droppableId;

    if (sourceId === destId) {
      return;
    }

    const [sourceDia, sourceHora] = sourceId.split('-');
    const [destDia, destHora] = destId.split('-');

    const sourceCell = getCellData(sourceDia, sourceHora);
    const destCell = getCellData(destDia, destHora);

    const blockId = result.draggableId;
    const block = sourceCell.bloques.find((b) => b.id === blockId);

    if (!block) return;

    const previousSchedule = JSON.parse(JSON.stringify(scheduleData));

    try {
      const sourceHoraData = estructura_horas.find((h) => h.inicio === sourceHora);
      const destHoraData = estructura_horas.find((h) => h.inicio === destHora);

      await axios.post(`${API}/schedule/${scheduleId}/move-block`, {
        block_id: blockId,
        from_dia: sourceDia,
        from_hora_inicio: sourceHora,
        from_hora_fin: sourceHoraData?.fin || sourceHora,
        to_dia: destDia,
        to_hora_inicio: destHora,
        to_hora_fin: destHoraData?.fin || destHora,
      });

      const updatedSchedule = { ...scheduleData };
      const updatedSourceCell = updatedSchedule.celdas.find(
        (c) => c.dia === sourceDia && c.hora_inicio === sourceHora
      );
      updatedSourceCell.bloques = updatedSourceCell.bloques.filter((b) => b.id !== blockId);

      let updatedDestCell = updatedSchedule.celdas.find(
        (c) => c.dia === destDia && c.hora_inicio === destHora
      );

      if (!updatedDestCell) {
        updatedDestCell = {
          dia: destDia,
          hora_inicio: destHora,
          hora_fin: destHoraData?.fin || destHora,
          bloques: [],
          celda_ref: null,
        };
        updatedSchedule.celdas.push(updatedDestCell);
      }

      updatedDestCell.bloques.push(block);

      setScheduleData(updatedSchedule);

      pushAction({
        type: 'MOVE_BLOCK',
        data: {
          blockId,
          from: { dia: sourceDia, hora: sourceHora },
          to: { dia: destDia, hora: destHora },
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

      toast.success('Bloque movido exitosamente');
    } catch (error) {
      console.error('Error moving block:', error);
      setScheduleData(previousSchedule);
      toast.error('Error al mover el bloque');
    }
  };

  const getBlockClass = (estado) => {
    const baseClass = 'block-item';
    switch (estado) {
      case 'confirmed':
        return `${baseClass} block-confirmed`;
      case 'inferred':
        return `${baseClass} block-inferred`;
      case 'error':
        return `${baseClass} block-error`;
      default:
        return `${baseClass} block-unknown`;
    }
  };

  const getStatusIndicator = (estado, confianza) => {
    const pct = Math.round((confianza || 0) * 100);
    switch (estado) {
      case 'confirmed':
        return { color: 'bg-emerald-500', shadow: 'shadow-emerald-200', title: `Confirmado (${pct}%)` };
      case 'inferred':
        return { color: 'bg-amber-500', shadow: 'shadow-amber-200', title: `Dudoso/Inferido (${pct}%)` };
      case 'error':
        return { color: 'bg-rose-500', shadow: 'shadow-rose-200', title: `Error de extracción (${pct}%)` };
      default:
        return { color: 'bg-slate-400', shadow: 'shadow-slate-200', title: `Desconocido` };
    }
  };

  return (
    <>
      <DragDropContext onDragStart={onDragStart} onDragEnd={onDragEnd}>
        <table className="schedule-grid">
          <thead>
            <tr>
              <th style={{ width: '100px' }}>Hora</th>
              {estructura_dias.map((dia) => (
                <th key={dia} style={{ width: '200px' }}>
                  {dia}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {estructura_horas.map((hora) => (
              <tr key={`${hora.inicio}-${hora.fin}`}>
                <td className="text-xs text-slate-600 p-2">
                  <div>{hora.inicio}</div>
                  <div>{hora.fin}</div>
                </td>
                {estructura_dias.map((dia) => {
                  const cellData = getCellData(dia, hora.inicio);
                  const cellId = getCellId(dia, hora.inicio);
                  const isSelected =
                    selectedCell?.dia === dia &&
                    selectedCell?.hora_inicio === hora.inicio;

                  return (
                    <td
                      key={cellId}
                      className={`schedule-cell ${isSelected ? 'selected' : ''}`}
                      onClick={() =>
                        handleCellClick(dia, hora.inicio, cellData?.celda_ref)
                      }
                      data-testid={`schedule-cell-${dia}-${hora.inicio}`}
                    >
                      <Droppable droppableId={cellId}>
                        {(provided, snapshot) => {
                          const bloques = cellData?.bloques || [];
                          const hasMultipleBlocks = bloques.length > 1;
                          const isExpanded = isCellExpanded(cellId);
                          const displayBlocks = isExpanded ? bloques : bloques.slice(0, 1);
                          const isEmpty = bloques.length === 0;

                          return (
                            <div
                              ref={provided.innerRef}
                              {...provided.droppableProps}
                              className={`min-h-[60px] relative group ${
                                snapshot.isDraggingOver ? 'bg-blue-50' : ''
                              }`}
                            >
                              {displayBlocks.map((block, index) => {
                                const isSelected = selectedBlockIds.has(block.id);
                                return (
                                <Draggable
                                  key={block.id}
                                  draggableId={block.id}
                                  index={index}
                                  isDragDisabled={selectionMode}
                                >
                                  {(provided, snapshot) => {
                                    const statusConfig = getStatusIndicator(block.estado, block.nivel_confianza);
                                    return (
                                      <div
                                        ref={provided.innerRef}
                                        {...provided.draggableProps}
                                        {...provided.dragHandleProps}
                                        className={`${getBlockClass(block.estado)} ${
                                          snapshot.isDragging ? 'shadow-lg' : ''
                                        } ${
                                          isSelected ? 'ring-2 ring-blue-500 ring-offset-1' : ''
                                        } ${selectionMode ? 'cursor-pointer' : ''} relative`}
                                        onClick={(e) => handleBlockClick(block, e, dia, hora.inicio, cellData?.celda_ref)}
                                        data-testid={`block-${block.id}`}
                                      >
                                        {/* Semáforo de confianza */}
                                        <div 
                                          className={`absolute top-2 right-2 w-2.5 h-2.5 rounded-full shadow-sm ${statusConfig.color} ${statusConfig.shadow}`}
                                          title={statusConfig.title}
                                        />

                                        {selectionMode && (
                                          <div
                                            className={`absolute top-1 right-6 w-4 h-4 rounded-sm border flex items-center justify-center ${
                                              isSelected
                                                ? 'bg-blue-600 border-blue-600 text-white'
                                                : 'bg-white border-slate-300'
                                            }`}
                                            data-testid={`block-checkbox-${block.id}`}
                                          >
                                            {isSelected && <Check className="w-3 h-3" />}
                                          </div>
                                        )}
                                        <div className="font-medium text-slate-900 pr-5">
                                          {block.materia}
                                        </div>
                                        {block.grupo && (
                                          <div className="text-slate-600">({block.grupo})</div>
                                        )}
                                        {block.docente && (
                                          <div className="text-blue-600 text-[10px] mt-1 flex items-center gap-0.5">
                                            <span title="Docente">👤</span>
                                            <span>{block.docente}</span>
                                          </div>
                                        )}
                                        {block.aula && (
                                          <div className="text-emerald-600 text-[10px] flex items-center gap-0.5">
                                            <span title="Aula">📍</span>
                                            <span>{block.aula}</span>
                                          </div>
                                        )}
                                      </div>
                                    );
                                  }}
                                </Draggable>
                                );
                              })}

                              {hasMultipleBlocks && (
                                <button
                                  onClick={(e) => toggleCellExpansion(cellId, e)}
                                  className="w-full mt-1 px-2 py-1 text-[10px] font-medium text-blue-600 hover:bg-blue-50 rounded border border-blue-200 transition-colors flex items-center justify-center gap-1"
                                  data-testid={`expand-btn-${cellId}`}
                                >
                                  {isExpanded ? (
                                    <>
                                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                                      </svg>
                                      Ocultar
                                    </>
                                  ) : (
                                    <>
                                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                      </svg>
                                      +{bloques.length - 1} más
                                    </>
                                  )}
                                </button>
                              )}

                              {isEmpty && !selectionMode && !isLocked && (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setNewBlockSlot({ dia, hora_inicio: hora.inicio, hora_fin: hora.fin });
                                  }}
                                  className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity text-slate-400 hover:text-blue-600 hover:bg-blue-50/50"
                                  data-testid={`add-block-${dia}-${hora.inicio}`}
                                  title="Agregar materia"
                                >
                                  <Plus className="w-5 h-5" />
                                </button>
                              )}

                              {provided.placeholder}
                            </div>
                          );
                        }}
                      </Droppable>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </DragDropContext>

      {editingBlock && (
        <BlockEditor
          block={editingBlock}
          onClose={() => setEditingBlock(null)}
        />
      )}

      {selectionMode && selectedBlockIds.size > 0 && (
        <div
          className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-white shadow-xl border border-slate-200 rounded-full px-4 py-2 flex items-center gap-3"
          data-testid="multi-edit-fab"
        >
          <span className="text-sm font-medium text-slate-700">
            {selectedBlockIds.size} bloque(s) seleccionado(s)
          </span>
          <button
            onClick={() => setShowMultiEditor(true)}
            className="px-3 py-1.5 bg-blue-600 text-white text-sm rounded-full hover:bg-blue-700 transition-colors font-medium"
            data-testid="multi-edit-open-btn"
          >
            Editar
          </button>
        </div>
      )}

      {showMultiEditor && (
        <MultiBlockEditor onClose={() => setShowMultiEditor(false)} />
      )}

      {newBlockSlot && (
        <NewBlockDialog
          cellSlot={newBlockSlot}
          onClose={() => setNewBlockSlot(null)}
        />
      )}
    </>
  );
};

export default ScheduleGrid;
