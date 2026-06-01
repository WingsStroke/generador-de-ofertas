import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import * as XLSX from 'xlsx';
import { Upload as UploadIcon, FileSpreadsheet, FileText, CheckCircle, GraduationCap, FileJson, AlertCircle, ChevronDown, ChevronUp, Users } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Label } from '../components/ui/label';
import { toast } from 'sonner';
import { useSchedule } from '../context/ScheduleContext';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = BACKEND_URL ? `${BACKEND_URL}/api` : '/api';

const Upload = () => {
  const [mode, setMode] = useState('xlsx');
  const [file, setFile] = useState(null);
  const [jsonFile, setJsonFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [importingJson, setImportingJson] = useState(false);
  const [jsonErrors, setJsonErrors] = useState([]);
  const [showErrors, setShowErrors] = useState(false);
  const [programs, setPrograms] = useState([]);
  const [selectedProgram, setSelectedProgram] = useState('ingenieria_de_sistemas');
  const [isDragOverXlsx, setIsDragOverXlsx] = useState(false);
  const [isDragOverJson, setIsDragOverJson] = useState(false);
  const navigate = useNavigate();
  const { setExcelHtmlBySheet } = useSchedule();

  useEffect(() => {
    const prevent = (e) => e.preventDefault();
    document.addEventListener('dragover', prevent);
    document.addEventListener('drop', prevent);
    return () => {
      document.removeEventListener('dragover', prevent);
      document.removeEventListener('drop', prevent);
    };
  }, []);

  useEffect(() => {
    const fetchPrograms = async () => {
      try {
        const response = await axios.get(`${API}/programs`);
        setPrograms(response.data);
      } catch (error) {
        console.error('Error fetching programs:', error);
      }
    };
    fetchPrograms();
  }, []);

  const readXlsxAsHtml = (selectedFile) => {
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = (evt) => {
        try {
          const data = new Uint8Array(evt.target.result);
          const workbook = XLSX.read(data, { type: 'array' });
          const htmlMap = {};
          workbook.SheetNames.forEach((sheetName) => {
            const ws = workbook.Sheets[sheetName];
            htmlMap[sheetName] = XLSX.utils.sheet_to_html(ws, {
              id: `xlsx-sheet-${sheetName}`,
              editable: false,
            });
          });
          resolve(htmlMap);
        } catch (err) {
          console.error('Error leyendo XLSX con SheetJS:', err);
          resolve({});
        }
      };
      reader.readAsArrayBuffer(selectedFile);
    });
  };

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) setFile(selectedFile);
  };

  const handleJsonFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) { setJsonFile(selectedFile); setJsonErrors([]); }
  };

  const handleXlsxDrop = (e) => {
    e.preventDefault();
    setIsDragOverXlsx(false);
    const dropped = e.dataTransfer.files[0];
    if (!dropped) return;
    if (dropped.name.match(/\.(xlsx|xls|pdf)$/i)) {
      setFile(dropped);
    } else {
      toast.error('Solo se aceptan archivos Excel (.xlsx, .xls) o PDF (.pdf)');
    }
  };

  const handleJsonDrop = (e) => {
    e.preventDefault();
    setIsDragOverJson(false);
    const dropped = e.dataTransfer.files[0];
    if (!dropped) return;
    if (dropped.name.endsWith('.json')) {
      setJsonFile(dropped);
      setJsonErrors([]);
    } else {
      toast.error('Solo se aceptan archivos JSON (.json)');
    }
  };

  const handleImportJson = async () => {
    if (!jsonFile) {
      toast.error('Por favor selecciona un archivo JSON');
      return;
    }
    setImportingJson(true);
    setJsonErrors([]);
    try {
      const text = await jsonFile.text();
      let parsed;
      try {
        parsed = JSON.parse(text);
      } catch (e) {
        setJsonErrors([`JSON inválido: ${e.message}`]);
        setShowErrors(true);
        return;
      }
      const response = await axios.post(`${API}/import-json`, parsed, {
        headers: { 'Content-Type': 'application/json' },
      });
      toast.success(`Importado: ${response.data.programa} (${response.data.semestres} semestres)`);
      navigate(`/dashboard/${response.data.schedule_id}`);
    } catch (error) {
      if (error.response?.status === 422) {
        const detail = error.response.data?.detail;
        const errs = detail?.errors || [detail?.message || 'Error de validación'];
        setJsonErrors(errs);
        setShowErrors(true);
      } else {
        toast.error('Error al importar el JSON');
      }
    } finally {
      setImportingJson(false);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      toast.error('Por favor selecciona un archivo');
      return;
    }

    if (!selectedProgram) {
      toast.error('Por favor selecciona un programa académico');
      return;
    }

    setUploading(true);

    // Solo intentar leer el XLSX localmente si NO es un PDF
    // (los PDFs los convierte el backend directamente)
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      const htmlMap = await readXlsxAsHtml(file);
      setExcelHtmlBySheet(htmlMap);
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post(`${API}/upload?program_id=${selectedProgram}`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      toast.success('Archivo procesado exitosamente');
      navigate(`/dashboard/${response.data.schedule_id}`);
    } catch (error) {
      console.error('Error uploading file:', error);
      toast.error('Error al procesar el archivo');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 flex flex-col relative">
      <header className="w-full p-4 flex justify-end">
        <Link to="/teachers">
          <Button variant="outline" className="bg-white hover:bg-slate-50 shadow-sm border-slate-200">
            <Users className="w-4 h-4 mr-2 text-blue-600" />
            Diccionario de Docentes
          </Button>
        </Link>
      </header>

      <div className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-2xl">
          <div className="text-center mb-8">
            <h1 className="text-4xl font-bold text-slate-900 mb-3 tracking-tight">
              Validador de Horarios Académicos
            </h1>
            <p className="text-lg text-slate-600">
              Sube un archivo Excel o importa un JSON exportado previamente
            </p>
          </div>

          {/* Tabs de modo */}
          <div className="flex rounded-lg border border-slate-200 bg-slate-100 p-1 mb-4">
            <button
              onClick={() => { setMode('xlsx'); setFile(null); setJsonFile(null); setJsonErrors([]); }}
              className={`flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-md text-sm font-medium transition-all ${mode === 'xlsx' ? 'bg-white shadow-sm text-blue-700' : 'text-slate-600 hover:text-slate-900'
                }`}
            >
              <FileSpreadsheet className="w-4 h-4" />
              Desde Excel o PDF
            </button>
            <button
              onClick={() => { setMode('json'); setFile(null); setJsonFile(null); setJsonErrors([]); }}
              className={`flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-md text-sm font-medium transition-all ${mode === 'json' ? 'bg-white shadow-sm text-emerald-700' : 'text-slate-600 hover:text-slate-900'
                }`}
            >
              <FileJson className="w-4 h-4" />
              Importar JSON
            </button>
          </div>

          <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-8">
            {mode === 'xlsx' ? (
              <div className="space-y-6">
                <div className="space-y-2">
                  <Label htmlFor="program-select" className="text-sm font-medium text-slate-700">
                    Programa Académico
                  </Label>
                  <Select value={selectedProgram} onValueChange={setSelectedProgram}>
                    <SelectTrigger id="program-select" className="w-full" data-testid="program-select">
                      <SelectValue placeholder="Selecciona un programa" />
                    </SelectTrigger>
                    <SelectContent>
                      {programs.map((program) => (
                        <SelectItem key={program.id} value={program.id} data-testid={`program-${program.id}`}>
                          <div className="flex items-center gap-2">
                            <GraduationCap className="w-4 h-4 text-blue-600" />
                            <span>{program.nombre}</span>
                            <span className="text-xs text-slate-500">({program.total_materias} materias)</span>
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {!file ? (
                  <label
                    htmlFor="file-upload"
                    className={`flex flex-col items-center justify-center w-full h-56 border-2 border-dashed rounded-lg cursor-pointer transition-all duration-150 ${isDragOverXlsx ? 'border-blue-500 bg-blue-50 scale-[1.01]' : 'border-slate-300 hover:border-blue-500 hover:bg-slate-50'}`}
                    data-testid="file-upload-area"
                    onDragOver={(e) => { e.preventDefault(); setIsDragOverXlsx(true); }}
                    onDragLeave={() => setIsDragOverXlsx(false)}
                    onDrop={handleXlsxDrop}
                  >
                    <div className="flex flex-col items-center justify-center pt-5 pb-6 pointer-events-none">
                      <div className={`w-14 h-14 rounded-full flex items-center justify-center mb-4 ${isDragOverXlsx ? 'bg-blue-200' : 'bg-blue-100'}`}>
                        {file?.name?.toLowerCase().endsWith('.pdf')
                          ? <FileText className="w-7 h-7 text-blue-600" />
                          : <FileSpreadsheet className="w-7 h-7 text-blue-600" />}
                      </div>
                      <p className="mb-2 text-base font-medium text-slate-700">
                        {isDragOverXlsx ? <span className="text-blue-600">Suelta el archivo aqui</span> : <><span className="text-blue-600">Haz clic para seleccionar</span> o arrastra un archivo</>}
                      </p>
                      <p className="text-sm text-slate-500">Excel (.xlsx, .xls) o PDF (.pdf)</p>
                    </div>
                    <input
                      id="file-upload"
                      type="file"
                      className="hidden"
                      accept=".xlsx,.xls,.pdf,application/pdf"
                      onChange={handleFileChange}
                      data-testid="file-input"
                    />
                  </label>
                ) : (
                  <div className="space-y-4">
                    <div className="flex items-center gap-3 p-4 bg-slate-50 rounded-lg border border-slate-200">
                      <CheckCircle className="w-5 h-5 text-green-600" />
                      <div className="flex-1">
                        <p className="text-sm font-medium text-slate-900">{file.name}</p>
                        <p className="text-xs text-slate-500">{(file.size / 1024).toFixed(2)} KB</p>
                      </div>
                      <Button variant="ghost" size="sm" onClick={() => setFile(null)} data-testid="remove-file-btn">
                        Cambiar
                      </Button>
                    </div>
                    <Button onClick={handleUpload} disabled={uploading} className="w-full" size="lg" data-testid="upload-btn">
                      {uploading ? <span>Procesando...</span> : <><UploadIcon className="w-5 h-5 mr-2" />Procesar Archivo</>}
                    </Button>
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-6">
                <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-4 text-sm text-emerald-800">
                  Importa un archivo <strong>.json</strong> exportado previamente desde esta aplicación.
                  El sistema validará su estructura y te mostrará los errores si los hay.
                </div>

                {!jsonFile ? (
                  <label
                    htmlFor="json-upload"
                    className={`flex flex-col items-center justify-center w-full h-56 border-2 border-dashed rounded-lg cursor-pointer transition-all duration-150 ${isDragOverJson ? 'border-emerald-500 bg-emerald-50 scale-[1.01]' : 'border-slate-300 hover:border-emerald-500 hover:bg-slate-50'}`}
                    onDragOver={(e) => { e.preventDefault(); setIsDragOverJson(true); }}
                    onDragLeave={() => setIsDragOverJson(false)}
                    onDrop={handleJsonDrop}
                  >
                    <div className="flex flex-col items-center justify-center pt-5 pb-6 pointer-events-none">
                      <div className={`w-14 h-14 rounded-full flex items-center justify-center mb-4 ${isDragOverJson ? 'bg-emerald-200' : 'bg-emerald-100'}`}>
                        <FileJson className="w-7 h-7 text-emerald-600" />
                      </div>
                      <p className="mb-2 text-base font-medium text-slate-700">
                        {isDragOverJson ? <span className="text-emerald-600">Suelta el archivo aqui</span> : <><span className="text-emerald-600">Haz clic para seleccionar</span> o arrastra un archivo</>}
                      </p>
                      <p className="text-sm text-slate-500">Archivo JSON (.json)</p>
                    </div>
                    <input
                      id="json-upload"
                      type="file"
                      className="hidden"
                      accept=".json,application/json"
                      onChange={handleJsonFileChange}
                    />
                  </label>
                ) : (
                  <div className="space-y-4">
                    <div className="flex items-center gap-3 p-4 bg-slate-50 rounded-lg border border-slate-200">
                      <CheckCircle className="w-5 h-5 text-emerald-600" />
                      <div className="flex-1">
                        <p className="text-sm font-medium text-slate-900">{jsonFile.name}</p>
                        <p className="text-xs text-slate-500">{(jsonFile.size / 1024).toFixed(2)} KB</p>
                      </div>
                      <Button variant="ghost" size="sm" onClick={() => { setJsonFile(null); setJsonErrors([]); }}>
                        Cambiar
                      </Button>
                    </div>

                    {jsonErrors.length > 0 && (
                      <div className="rounded-lg border border-red-200 bg-red-50 overflow-hidden">
                        <button
                          onClick={() => setShowErrors((v) => !v)}
                          className="w-full flex items-center justify-between px-4 py-3 text-sm font-semibold text-red-700 hover:bg-red-100 transition-colors"
                        >
                          <span className="flex items-center gap-2">
                            <AlertCircle className="w-4 h-4" />
                            {jsonErrors.length} error{jsonErrors.length !== 1 ? 'es' : ''} encontrado{jsonErrors.length !== 1 ? 's' : ''} — corrígelos antes de importar
                          </span>
                          {showErrors ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                        </button>
                        {showErrors && (
                          <ul className="px-4 pb-3 space-y-1 max-h-48 overflow-y-auto">
                            {jsonErrors.map((err, i) => (
                              <li key={i} className="text-xs text-red-700 font-mono bg-red-100 rounded px-2 py-1">
                                {err}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )}

                    <Button
                      onClick={handleImportJson}
                      disabled={importingJson}
                      className="w-full bg-emerald-600 hover:bg-emerald-700"
                      size="lg"
                    >
                      {importingJson ? <span>Importando...</span> : <><UploadIcon className="w-5 h-5 mr-2" />Importar JSON</>}
                    </Button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Upload;
