import React, { useMemo, useState, useRef, useEffect } from 'react';
import { useSchedule } from '../context/ScheduleContext';
import '@/App.css';

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 2.0;
const ZOOM_STEP = 0.1;
const ZOOM_DEFAULT = 0.75;

const ZoomControls = ({ zoom, onZoom, onReset }) => (
  <div className="excel-zoom-controls">
    <button
      className="excel-zoom-btn"
      onClick={() => onZoom(-ZOOM_STEP)}
      disabled={zoom <= ZOOM_MIN}
      title="Reducir zoom"
      aria-label="Reducir zoom"
    >
      −
    </button>
    <button
      className="excel-zoom-label"
      onClick={onReset}
      title="Restablecer zoom (75%)"
    >
      {Math.round(zoom * 100)}%
    </button>
    <button
      className="excel-zoom-btn"
      onClick={() => onZoom(+ZOOM_STEP)}
      disabled={zoom >= ZOOM_MAX}
      title="Ampliar zoom"
      aria-label="Ampliar zoom"
    >
      +
    </button>
  </div>
);

const ZoomedContent = ({ zoom, children }) => {
  const innerRef = useRef(null);
  const [scaledHeight, setScaledHeight] = useState('auto');

  useEffect(() => {
    if (!innerRef.current) return;
    const observer = new ResizeObserver(() => {
      if (innerRef.current) {
        setScaledHeight(innerRef.current.scrollHeight * zoom);
      }
    });
    observer.observe(innerRef.current);
    setScaledHeight(innerRef.current.scrollHeight * zoom);
    return () => observer.disconnect();
  }, [zoom]);

  return (
    <div style={{ height: scaledHeight, position: 'relative', minHeight: 0 }}>
      <div
        ref={innerRef}
        style={{
          transform: `scale(${zoom})`,
          transformOrigin: 'top left',
          width: `${Math.round((1 / zoom) * 10000) / 100}%`,
        }}
      >
        {children}
      </div>
    </div>
  );
};

const ExcelPreviewFallback = ({ excel_preview, selectedCell }) => {
  const grid = useMemo(() => {
    if (!excel_preview || excel_preview.length === 0) return [];
    const maxRow = Math.max(...excel_preview.map((c) => c.row));
    const maxCol = Math.max(...excel_preview.map((c) => c.col));
    const rows = [];
    for (let r = 1; r <= maxRow; r++) {
      const row = [];
      for (let c = 1; c <= maxCol; c++) {
        const cell = excel_preview.find((cell) => cell.row === r && cell.col === c);
        row.push(cell || { ref: `${String.fromCharCode(64 + c)}${r}`, value: null, row: r, col: c, rowspan: 1, colspan: 1 });
      }
      rows.push(row);
    }
    return rows;
  }, [excel_preview]);

  if (grid.length === 0) return null;

  return (
    <table className="excel-preview-grid">
      <tbody>
        {grid.map((row, rowIdx) => (
          <tr key={rowIdx}>
            {row.map((cell) => {
              if (cell.rowspan === 0 || cell.colspan === 0) return null;
              const highlighted = selectedCell?.celda_ref === cell.ref;
              return (
                <td
                  key={cell.ref}
                  rowSpan={cell.rowspan || 1}
                  colSpan={cell.colspan || 1}
                  className={highlighted ? 'highlighted' : ''}
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

const ExcelPreview = () => {
  const { scheduleData, selectedCell, excelHtmlBySheet } = useSchedule();
  const [zoom, setZoom] = useState(ZOOM_DEFAULT);

  const currentSheet = scheduleData?.hoja_actual;
  const sheetHtml = currentSheet ? excelHtmlBySheet?.[currentSheet] : null;

  const handleZoom = (delta) => {
    setZoom((prev) => {
      const next = Math.round((prev + delta) * 10) / 10;
      return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, next));
    });
  };

  const content = sheetHtml ? (
    <div
      className="xlsx-sheetjs-preview"
      dangerouslySetInnerHTML={{ __html: sheetHtml }}
    />
  ) : scheduleData?.excel_preview ? (
    <ExcelPreviewFallback
      excel_preview={scheduleData.excel_preview}
      selectedCell={selectedCell}
    />
  ) : null;

  if (!content) return null;

  return (
    <div className="excel-preview-wrapper">
      <ZoomControls zoom={zoom} onZoom={handleZoom} onReset={() => setZoom(ZOOM_DEFAULT)} />
      <div className="excel-preview-scroll">
        <ZoomedContent zoom={zoom}>
          {content}
        </ZoomedContent>
      </div>
    </div>
  );
};

export default ExcelPreview;
