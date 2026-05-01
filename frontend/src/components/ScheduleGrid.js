import React, { useState } from 'react';
import { useSchedule } from '../context/ScheduleContext';
import BlockEditor from './BlockEditor';
import '@/App.css';

const ScheduleGrid = () => {
  const { scheduleData, selectedCell, setSelectedCell } = useSchedule();
  const [editingBlock, setEditingBlock] = useState(null);

  if (!scheduleData) return null;

  const { estructura_dias, estructura_horas, celdas } = scheduleData;

  const getCellData = (dia, hora_inicio) => {
    return celdas.find(
      (c) => c.dia === dia && c.hora_inicio === hora_inicio
    );
  };

  const handleCellClick = (dia, hora_inicio, celda_ref) => {
    setSelectedCell({ dia, hora_inicio, celda_ref });
  };

  const handleBlockClick = (block, e) => {
    e.stopPropagation();
    setEditingBlock(block);
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
                const isSelected =
                  selectedCell?.dia === dia &&
                  selectedCell?.hora_inicio === hora.inicio;

                return (
                  <td
                    key={`${dia}-${hora.inicio}`}
                    className={`schedule-cell ${isSelected ? 'selected' : ''}`}
                    onClick={() =>
                      handleCellClick(dia, hora.inicio, cellData?.celda_ref)
                    }
                    data-testid={`schedule-cell-${dia}-${hora.inicio}`}
                  >
                    {cellData?.bloques.map((block) => (
                      <div
                        key={block.id}
                        className={getBlockClass(block.estado)}
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
                    ))}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

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
