import React from 'react';
import { useSchedule } from '../context/ScheduleContext';
import '@/App.css';

const ExcelPreview = () => {
  const { scheduleData, selectedCell } = useSchedule();

  if (!scheduleData || !scheduleData.excel_preview) return null;

  const { excel_preview } = scheduleData;

  const maxRow = Math.max(...excel_preview.map((c) => c.row));
  const maxCol = Math.max(...excel_preview.map((c) => c.col));

  const grid = [];
  for (let r = 1; r <= maxRow; r++) {
    const row = [];
    for (let c = 1; c <= maxCol; c++) {
      const cell = excel_preview.find((cell) => cell.row === r && cell.col === c);
      if (cell) {
        row.push(cell);
      } else {
        row.push({ ref: `${String.fromCharCode(64 + c)}${r}`, value: null, row: r, col: c });
      }
    }
    grid.push(row);
  }

  const isHighlighted = (cellRef) => {
    return selectedCell?.celda_ref === cellRef;
  };

  return (
    <table className="excel-preview-grid">
      <tbody>
        {grid.map((row, rowIdx) => (
          <tr key={rowIdx}>
            {row.map((cell) => {
              if (cell.rowspan === 0 || cell.colspan === 0) return null;

              return (
                <td
                  key={cell.ref}
                  rowSpan={cell.rowspan || 1}
                  colSpan={cell.colspan || 1}
                  className={isHighlighted(cell.ref) ? 'highlighted' : ''}
                  data-testid={`excel-preview-cell-${cell.ref}`}
                >
                  {cell.value && cell.value !== 'None' ? cell.value : ''}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
};

export default ExcelPreview;
