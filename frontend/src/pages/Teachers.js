import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Trash2, Users, Search, Plus, ArrowLeft, AlertTriangle, Check, X, ArrowDownAZ, ArrowUpZA, Edit2 } from 'lucide-react';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { toast } from 'sonner';
import { Link } from 'react-router-dom';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = BACKEND_URL ? `${BACKEND_URL}/api` : '/api';

const Teachers = () => {
  const [teachers, setTeachers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [newTeacherName, setNewTeacherName] = useState('');
  const [adding, setAdding] = useState(false);
  const [sortOrder, setSortOrder] = useState('asc');

  // Estado para el diálogo de confirmación de similares
  const [similarWarning, setSimilarWarning] = useState(null);
  // { normalized: str, similar: [[name, score], ...] }

  const [editingTeacher, setEditingTeacher] = useState(null);
  const [editName, setEditName] = useState('');

  useEffect(() => {
    fetchTeachers();
  }, []);

  const fetchTeachers = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${API}/teachers?t=${Date.now()}`, {
        headers: { 'Cache-Control': 'no-cache' }
      });
      setTeachers(response.data.teachers || []);
    } catch (error) {
      console.error('Error fetching teachers:', error);
      toast.error('Error al cargar la lista de docentes');
    } finally {
      setLoading(false);
    }
  };

  const handleAddTeacher = async (e, forceAdd = false) => {
    if (e) e.preventDefault();
    const nameToAdd = forceAdd ? similarWarning?.normalized : newTeacherName;
    if (!nameToAdd?.trim()) return;

    setAdding(true);
    try {
      const response = await axios.post(`${API}/teachers`, {
        name: nameToAdd,
        force: forceAdd
      });

      if (response.data.requires_confirmation) {
        // El backend encontró similares → mostrar advertencia
        setSimilarWarning({
          normalized: response.data.normalized,
          similar: response.data.similar || []
        });
        return;
      }

      if (response.data.added) {
        toast.success(`Docente "${response.data.normalized}" añadido al diccionario`);
        setNewTeacherName('');
        setSimilarWarning(null);
        fetchTeachers();
      } else {
        toast.info('El docente ya existe en el diccionario');
        setSimilarWarning(null);
      }
    } catch (error) {
      console.error('Error adding teacher:', error);
      toast.error('Error al añadir docente');
    } finally {
      setAdding(false);
    }
  };

  const handleCancelSimilar = () => {
    setSimilarWarning(null);
    setAdding(false);
  };

  const handleForceAdd = () => {
    handleAddTeacher(null, true);
  };

  const handleDeleteTeacher = async (name) => {
    if (!window.confirm(`¿Estás seguro de eliminar a "${name}" del diccionario?`)) return;

    // Optimistic update: quitar inmediatamente de la UI
    setTeachers(prev => prev.filter(t => t !== name));

    try {
      await axios.delete(`${API}/teachers/${encodeURIComponent(name)}`);
      toast.success('Docente eliminado');
      // Sync silencioso para asegurar consistencia
      axios.get(`${API}/teachers?t=${Date.now()}`).then(res => {
        if (res.data?.teachers) setTeachers(res.data.teachers);
      }).catch(console.error);
    } catch (error) {
      // Si hay error, restaurar el docente en la UI
      console.error('Error deleting teacher:', error);
      toast.error('Error al comunicarse con el servidor. Recargando lista...');
      fetchTeachers();
    }
  };

  const handleEditTeacher = async (oldName) => {
    if (!editName.trim() || editName.trim() === oldName) {
      setEditingTeacher(null);
      return;
    }

    const newName = editName.trim().toUpperCase();

    // Optimistic update
    setTeachers(prev => prev.map(t => t === oldName ? newName : t));
    setEditingTeacher(null);

    try {
      await axios.patch(`${API}/teachers/${encodeURIComponent(oldName)}`, { new_name: newName });
      toast.success('Docente renombrado');
      // Sync silencioso
      axios.get(`${API}/teachers?t=${Date.now()}`).then(res => {
        if (res.data?.teachers) setTeachers(res.data.teachers);
      }).catch(console.error);
    } catch (error) {
      console.error('Error editing teacher:', error);
      toast.error('Error al renombrar el docente');
      fetchTeachers(); // Restaurar en caso de fallo
    }
  };

  const filteredTeachers = teachers
    .filter(t => t.toLowerCase().includes(searchTerm.toLowerCase()))
    .sort((a, b) => {
      if (sortOrder === 'asc') {
        return a.localeCompare(b);
      } else {
        return b.localeCompare(a);
      }
    });

  return (
    <div className="h-screen bg-slate-50 flex flex-col">
      <header className="h-16 border-b border-slate-200 px-6 flex items-center justify-between bg-white z-50 sticky top-0 shadow-sm">
        <div className="flex items-center gap-4">
          <Link to="/">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="w-4 h-4 mr-2" />
              Volver al Inicio
            </Button>
          </Link>
          <div className="flex items-center gap-2">
            <Users className="w-5 h-5 text-blue-600" />
            <h1 className="text-xl font-semibold text-slate-900">
              Diccionario de Docentes
            </h1>
          </div>
        </div>
        <div className="text-sm text-slate-500">
          Total: <span className="font-semibold text-slate-700">{teachers.length}</span>
        </div>
      </header>

      <div className="flex-1 overflow-auto p-8">
        <div className="max-w-4xl mx-auto space-y-6">

          {/* ─── Panel de Añadir ─── */}
          <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
            <h2 className="text-lg font-medium text-slate-900 mb-4">Añadir Docente</h2>
            <form onSubmit={handleAddTeacher} className="flex gap-3">
              <Input
                value={newTeacherName}
                onChange={(e) => {
                  setNewTeacherName(e.target.value);
                  if (similarWarning) setSimilarWarning(null);
                }}
                placeholder="Nombre completo del docente..."
                className="flex-1"
                disabled={adding}
              />
              <Button type="submit" disabled={adding || !newTeacherName.trim()}>
                {adding ? 'Verificando...' : (
                  <>
                    <Plus className="w-4 h-4 mr-2" />
                    Añadir
                  </>
                )}
              </Button>
            </form>

            {/* Advertencia de similares */}
            {similarWarning && (
              <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                  <div className="flex-1">
                    <p className="text-sm font-semibold text-amber-800 mb-1">
                      ¿Posible duplicado?
                    </p>
                    <p className="text-xs text-amber-700 mb-2">
                      Se encontraron docentes similares en el diccionario. Puede ser el mismo docente con nombre abreviado o completo:
                    </p>
                    <ul className="space-y-1 mb-3">
                      {similarWarning.similar.map(([name, score]) => (
                        <li key={name} className="flex items-center justify-between text-xs bg-amber-100 rounded px-2 py-1.5">
                          <span className="font-mono font-medium text-amber-900">{name}</span>
                          <span className="text-amber-600 ml-2">Similitud: {score}%</span>
                        </li>
                      ))}
                    </ul>
                    <p className="text-xs text-amber-700 mb-3">
                      Nombre a añadir: <strong className="font-mono">{similarWarning.normalized}</strong>
                    </p>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        className="border-amber-300 text-amber-800 hover:bg-amber-100"
                        onClick={handleCancelSimilar}
                      >
                        <X className="w-3.5 h-3.5 mr-1.5" />
                        Cancelar
                      </Button>
                      <Button
                        size="sm"
                        className="bg-amber-600 hover:bg-amber-700 text-white"
                        onClick={handleForceAdd}
                        disabled={adding}
                      >
                        <Check className="w-3.5 h-3.5 mr-1.5" />
                        {adding ? 'Añadiendo...' : 'Sí, añadirlo de todas formas'}
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* ─── Lista de Docentes ─── */}
          <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200 flex flex-col h-[calc(100vh-280px)]">
            <div className="flex items-center gap-3 mb-4">
              <div className="relative flex-1">
                <Search className="w-5 h-5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <Input
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  placeholder="Buscar docente..."
                  className="pl-10"
                />
              </div>
              <Button
                variant="outline"
                className="flex gap-2 text-slate-600"
                onClick={() => setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc')}
                title={sortOrder === 'asc' ? "Ordenar Z-A" : "Ordenar A-Z"}
              >
                {sortOrder === 'asc' ? <ArrowDownAZ className="w-4 h-4" /> : <ArrowUpZA className="w-4 h-4" />}
                <span className="hidden sm:inline">
                  {sortOrder === 'asc' ? 'A-Z' : 'Z-A'}
                </span>
              </Button>
            </div>

            <div className="flex-1 overflow-auto border rounded-lg">
              {loading ? (
                <div className="h-full flex items-center justify-center text-slate-500">
                  Cargando...
                </div>
              ) : filteredTeachers.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-slate-400">
                  <Users className="w-12 h-12 mb-3 opacity-20" />
                  <p>No se encontraron docentes</p>
                </div>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {filteredTeachers.map((teacher, idx) => (
                    <li key={idx} className="flex items-center justify-between p-4 hover:bg-slate-50 group transition-colors">
                      {editingTeacher === teacher ? (
                        <div className="flex-1 flex items-center gap-2 mr-4">
                          <Input
                            autoFocus
                            value={editName}
                            onChange={(e) => setEditName(e.target.value.toUpperCase())}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') handleEditTeacher(teacher);
                              if (e.key === 'Escape') setEditingTeacher(null);
                            }}
                            className="h-8 text-sm"
                          />
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0 text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50"
                            onClick={() => handleEditTeacher(teacher)}
                          >
                            <Check className="w-4 h-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0 text-slate-500 hover:bg-slate-100"
                            onClick={() => setEditingTeacher(null)}
                          >
                            <X className="w-4 h-4" />
                          </Button>
                        </div>
                      ) : (
                        <>
                          <span className="font-medium text-slate-700">{teacher}</span>
                          <div className="flex items-center opacity-0 group-hover:opacity-100 transition-opacity">
                            <Button
                              variant="ghost"
                              size="icon"
                              className="text-blue-500 hover:bg-blue-50"
                              onClick={() => {
                                setEditingTeacher(teacher);
                                setEditName(teacher);
                              }}
                              title="Editar docente"
                            >
                              <Edit2 className="w-4 h-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="text-red-500 hover:bg-red-50"
                              onClick={() => handleDeleteTeacher(teacher)}
                              title="Eliminar docente"
                            >
                              <Trash2 className="w-4 h-4" />
                            </Button>
                          </div>
                        </>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
};

export default Teachers;
