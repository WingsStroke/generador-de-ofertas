import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Upload as UploadIcon, FileSpreadsheet, CheckCircle } from 'lucide-react';
import { Button } from '../components/ui/button';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const Upload = () => {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const navigate = useNavigate();

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      setFile(selectedFile);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      toast.error('Por favor selecciona un archivo');
      return;
    }

    setUploading(true);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post(`${API}/upload`, formData, {
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
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 flex items-center justify-center p-6">
      <div className="w-full max-w-2xl">
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-slate-900 mb-3 tracking-tight">
            Validador de Horarios Académicos
          </h1>
          <p className="text-lg text-slate-600">
            Sube un archivo Excel para extraer y validar la información
          </p>
        </div>

        <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-8">
          {!file ? (
            <label
              htmlFor="file-upload"
              className="flex flex-col items-center justify-center w-full h-64 border-2 border-dashed border-slate-300 rounded-lg cursor-pointer hover:border-blue-500 hover:bg-slate-50 transition-all duration-150"
              data-testid="file-upload-area"
            >
              <div className="flex flex-col items-center justify-center pt-5 pb-6">
                <div className="w-16 h-16 rounded-full bg-blue-100 flex items-center justify-center mb-4">
                  <FileSpreadsheet className="w-8 h-8 text-blue-600" />
                </div>
                <p className="mb-2 text-base font-medium text-slate-700">
                  <span className="text-blue-600">Haz clic para seleccionar</span> o arrastra un archivo
                </p>
                <p className="text-sm text-slate-500">Archivos Excel (.xlsx, .xls)</p>
              </div>
              <input
                id="file-upload"
                type="file"
                className="hidden"
                accept=".xlsx,.xls"
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
                  <p className="text-xs text-slate-500">
                    {(file.size / 1024).toFixed(2)} KB
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setFile(null)}
                  data-testid="remove-file-btn"
                >
                  Cambiar
                </Button>
              </div>

              <Button
                onClick={handleUpload}
                disabled={uploading}
                className="w-full"
                size="lg"
                data-testid="upload-btn"
              >
                {uploading ? (
                  <span>Procesando...</span>
                ) : (
                  <>
                    <UploadIcon className="w-5 h-5 mr-2" />
                    Procesar Archivo
                  </>
                )}
              </Button>
            </div>
          )}
        </div>

        <div className="mt-6 text-center">
          <p className="text-sm text-slate-600">
            El sistema extraerá automáticamente las materias, grupos, docentes y aulas
          </p>
        </div>
      </div>
    </div>
  );
};

export default Upload;
