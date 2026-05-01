import React, { useState } from 'react';
import { DragDropContext, Droppable, Draggable } from '@hello-pangea/dnd';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { useSchedule } from '../context/ScheduleContext';
import { useHistory } from '../context/HistoryContext';
import BlockEditor from './BlockEditor';
import { toast } from 'sonner';
import '@/App.css';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const ScheduleGrid = () => {
  const { scheduleId } = useParams();
  const { scheduleData, setScheduleData, selectedCell, setSelectedCell } = useSchedule();
  const { pushAction } = useHistory();
  const [editingBlock, setEditingBlock] = useState(null);
  const [isDragging, setIsDragging] = useState(false);

  if (!scheduleData) return null;

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

  const handleBlockClick = (block, e) => {
    e.stopPropagation();
    if (!isDragging) {
      setEditingBlock(block);
    }
  };

  const onDragStart = () => {
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
      const destHoraData = estructura_horas.find((h) => h.inicio === destHora);

      await axios.post(`${API}/schedule/${scheduleId}/move-block`, {
        block_id: blockId,
        from_dia: sourceDia,
        from_hora_inicio: sourceHora,
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
        },
        onRedo: () => {
          setScheduleData(updatedSchedule);
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
                        {(provided, snapshot) => (
                          <div
                            ref={provided.innerRef}
                            {...provided.droppableProps}
                            className={`min-h-[60px] ${
                              snapshot.isDraggingOver ? 'bg-blue-50' : ''
                            }`}
                          >
                            {cellData?.bloques.map((block, index) => (
                              <Draggable
                                key={block.id}
                                draggableId={block.id}
                                index={index}
                              >
                                {(provided, snapshot) => (
                                  <div
                                    ref={provided.innerRef}
                                    {...provided.draggableProps}
                                    {...provided.dragHandleProps}
                                    className={`${getBlockClass(block.estado)} ${
                                      snapshot.isDragging ? 'shadow-lg' : ''
                                    }`}
                                    onClick={(e) => handleBlockClick(block, e)}
                                    data-testid={`block-${block.id}`}
                                  >
                                    <div className="font-medium text-slate-900">
                                      {block.materia}
                                    </div>
                                    {block.grupo && (
                                      <div className="text-slate-600">({block.grupo})</div>
                                    )}
                                    {block.docente && (
                                      <div className="text-slate-600 text-[10px] mt-1">
                                        {block.docente}
                                      </div>
                                    )}
                                    {block.aula && (
                                      <div className="text-slate-500 text-[10px]">
                                        {block.aula}
                                      </div>
                                    )}
                                  </div>
                                )}
                              </Draggable>
                            ))}
                            {provided.placeholder}
                          </div>
                        )}
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
    </>
  );
};

export default ScheduleGrid;
