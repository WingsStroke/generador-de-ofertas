import React, { useMemo, useState, useRef, useEffect } from 'react';
import { useSchedule } from '../context/ScheduleContext';
import '@/App.css';

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 2.0;
const ZOOM_STEP = 0.1;
const ZOOM_DEFAULT = 0.75;

const sanitizeSheetHtml = (rawHtml) => {
  if (!rawHtml || typeof rawHtml !== 'string') return '';
  const parser = new DOMParser();
  const doc = parser.parseFromString(rawHtml, 'text/html');

  // Eliminar nodos potencialmente peligrosos aunque el backend ya escape valores.
  doc.querySelectorAll('script, iframe, object, embed, link[rel="import"], meta[http-equiv]').forEach((el) => el.remove());

  // Remover atributos inline que podrían ejecutar JS.
  doc.querySelectorAll('*').forEach((el) => {
    Array.from(el.attributes).forEach((attr) => {
      const name = attr.name.toLowerCase();
      const value = String(attr.value || '').toLowerCase();
      if (name.startsWith('on')) {
        el.removeAttribute(attr.name);
      }
      if ((name === 'src' || name === 'href') && value.startsWith('javascript:')) {
        el.removeAttribute(attr.name);
      }
    });
  });

  return doc.body.innerHTML;
};

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
  const { scheduleData, selectedCell, excelHtmlBySheet, loadingHtmlBySheet, zoom, setZoom } = useSchedule();
  const containerRef = useRef(null);

  const currentSheet = scheduleData?.hoja_actual;
  const sheetHtml = currentSheet ? excelHtmlBySheet?.[currentSheet] : null;
  const sanitizedSheetHtml = useMemo(() => sanitizeSheetHtml(sheetHtml), [sheetHtml]);
  const isLoading = currentSheet ? loadingHtmlBySheet?.[currentSheet] : false;

  useEffect(() => {
    if (!containerRef.current) return;
    
    // Remover highlights previos
    const prevHighlighted = containerRef.current.querySelectorAll('.xlsx-cell-highlight');
    prevHighlighted.forEach(el => el.classList.remove('xlsx-cell-highlight'));
    
    // Agregar highlight actual
    if (selectedCell?.celda_ref) {
      const cellToHighlight = containerRef.current.querySelector(`td[data-ref="${selectedCell.celda_ref}"]`);
      if (cellToHighlight) {
        cellToHighlight.classList.add('xlsx-cell-highlight');
        cellToHighlight.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
      }
    }
  }, [selectedCell, sheetHtml]);

  const handleZoom = (delta) => {
    setZoom((prev) => {
      const next = Math.round((prev + delta) * 10) / 10;
      return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, next));
    });
  };

  const content = isLoading ? (
    <div className="h-full flex items-center justify-center p-12">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
        <p className="text-slate-500 text-sm">Cargando vista original...</p>
      </div>
    </div>
  ) : sheetHtml ? (
    <div
      ref={containerRef}
      className="xlsx-html-preview"
      dangerouslySetInnerHTML={{ __html: sanitizedSheetHtml }}
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
