import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Search, X, FileText, MapPin, User, Book, Replace, RefreshCw } from 'lucide-react';
import { Input } from './ui/input';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { ScrollArea } from './ui/scroll-area';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Label } from './ui/label';
import { Checkbox } from './ui/checkbox';
import { toast } from 'sonner';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from './ui/sheet';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = BACKEND_URL ? `${BACKEND_URL}/api` : '/api';

const GlobalSearch = ({ onNavigate, currentSheet, onReplaceSuccess }) => {
  const { scheduleId } = useParams();
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [searchType, setSearchType] = useState('all');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [totalResults, setTotalResults] = useState(0);
  const [hojasCount, setHojasCount] = useState(0);

  // States for search and replace global
  const [replaceText, setReplaceText] = useState('');
  const [scope, setScope] = useState('current'); // 'current' or 'all'
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [exactMatch, setExactMatch] = useState(false);
  const [replacing, setReplacing] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        e.preventDefault();
        setIsOpen(true);
      }
      if (e.key === 'Escape' && isOpen) {
        setIsOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen]);

  useEffect(() => {
    if (query.length < 2) {
      setResults([]);
      setTotalResults(0);
      setHojasCount(0);
      return;
    }

    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const response = await axios.get(
          `${API}/schedule/${scheduleId}/search?q=${encodeURIComponent(query)}&type=${searchType}`
        );
        setResults(response.data.results || []);
        setTotalResults(response.data.total || 0);
        setHojasCount(response.data.hojas_con_resultados || 0);
      } catch (error) {
        console.error('Error searching:', error);
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [query, searchType, scheduleId]);

  const handleResultClick = (result) => {
    if (onNavigate) {
      onNavigate(result.hoja, result.dia, result.hora_inicio);
    }
    setIsOpen(false);
  };

  const clearSearch = () => {
    setQuery('');
    setResults([]);
    setTotalResults(0);
    setHojasCount(0);
  };

  const handleReplaceClick = async () => {
    if (!query) return;

    const scopeLabel = scope === 'current' ? `en la hoja actual ("${currentSheet}")` : 'en TODAS las hojas del horario';
    const confirmMessage = `¿Estás seguro de que deseas reemplazar todas las coincidencias de "${query}" por "${replaceText}" ${scopeLabel}?\n\nEsta acción modificará los datos de forma permanente.`;

    if (!window.confirm(confirmMessage)) {
      return;
    }

    setReplacing(true);
    try {
      const response = await axios.post(`${API}/schedule/${scheduleId}/replace`, {
        search_text: query,
        replace_text: replaceText,
        field: searchType,
        scope: scope,
        current_sheet: currentSheet,
        case_sensitive: caseSensitive,
        exact_match: exactMatch,
      });

      const { replaced_count, sheets_affected } = response.data;

      toast.success(
        `Se reemplazaron ${replaced_count} ocurrencias con éxito en ${sheets_affected.length} hoja(s).`
      );

      // Limpiar campos
      setQuery('');
      setReplaceText('');
      setResults([]);
      setTotalResults(0);
      setHojasCount(0);

      // Cerrar modal
      setIsOpen(false);

      // Notificar al componente padre
      if (onReplaceSuccess) {
        onReplaceSuccess(sheets_affected);
      }
    } catch (error) {
      console.error('Error replacing:', error);
      const detail = error?.response?.data?.detail || 'Error desconocido';
      toast.error(`Error al reemplazar: ${detail}`);
    } finally {
      setReplacing(false);
    }
  };

  const getFieldIcon = (field) => {
    switch (field) {
      case 'materia':
        return <Book className="w-4 h-4 text-blue-600" />;
      case 'docente':
        return <User className="w-4 h-4 text-purple-600" />;
      case 'aula':
        return <MapPin className="w-4 h-4 text-green-600" />;
      default:
        return <Search className="w-4 h-4 text-slate-600" />;
    }
  };

  const getStatusColor = (estado) => {
    switch (estado) {
      case 'confirmed':
        return 'bg-green-100 text-green-800';
      case 'inferred':
        return 'bg-yellow-100 text-yellow-800';
      case 'error':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <Sheet open={isOpen} onOpenChange={setIsOpen}>
      <SheetTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2" data-testid="global-search-btn">
          <Search className="w-4 h-4" />
          Buscar y Reemplazar
          <kbd className="hidden sm:inline-flex h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground opacity-100">
            <span className="text-xs">⌘</span>F
          </kbd>
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="w-full sm:max-w-xl flex flex-col h-full bg-white">
        <SheetHeader className="pb-4 border-b">
          <SheetTitle>Búsqueda y Reemplazo Global</SheetTitle>
          <SheetDescription>
            Busca y reemplaza textos en materias, docentes o aulas del horario
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-hidden flex flex-col mt-4 space-y-4">
          {/* Búsqueda */}
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-slate-400" />
              <Input
                placeholder="Buscar..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="pl-10 pr-10"
                autoFocus
                data-testid="search-input"
              />
              {query && (
                <button
                  onClick={clearSearch}
                  className="absolute right-3 top-1/2 transform -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  data-testid="clear-search-btn"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
            <Select value={searchType} onValueChange={setSearchType}>
              <SelectTrigger className="w-32" data-testid="search-type-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="materia">Materia</SelectItem>
                <SelectItem value="docente">Docente</SelectItem>
                <SelectItem value="aula">Aula</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Reemplazo */}
          <div className="border border-slate-100 bg-slate-50/70 p-4 rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                <Replace className="w-3.5 h-3.5 text-blue-600" /> Reemplazo Global
              </span>
              {query.length >= 2 && !loading && (
                <Badge variant="secondary" className="bg-blue-50 text-blue-700 font-medium">
                  {totalResults} coincidencia{totalResults !== 1 ? 's' : ''}
                </Badge>
              )}
            </div>

            <div className="flex gap-2">
              <div className="relative flex-1">
                <Replace className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-slate-400" />
                <Input
                  placeholder="Reemplazar con..."
                  value={replaceText}
                  onChange={(e) => setReplaceText(e.target.value)}
                  className="pl-10 pr-3"
                  data-testid="replace-input"
                />
              </div>
              <Select value={scope} onValueChange={setScope}>
                <SelectTrigger className="w-40" data-testid="replace-scope-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="current">Hoja actual</SelectItem>
                  <SelectItem value="all">Todas las hojas</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-wrap gap-4 pt-1">
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="case-sensitive"
                  checked={caseSensitive}
                  onCheckedChange={setCaseSensitive}
                />
                <Label htmlFor="case-sensitive" className="text-xs font-normal text-slate-600 cursor-pointer select-none">
                  Mayús/Minús
                </Label>
              </div>

              <div className="flex items-center space-x-2">
                <Checkbox
                  id="exact-match"
                  checked={exactMatch}
                  onCheckedChange={setExactMatch}
                />
                <Label htmlFor="exact-match" className="text-xs font-normal text-slate-600 cursor-pointer select-none">
                  Coincidencia exacta
                </Label>
              </div>
            </div>

            <div className="pt-1">
              <Button
                onClick={handleReplaceClick}
                disabled={replacing || !query || totalResults === 0}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white gap-2 transition-all font-medium"
                data-testid="global-replace-btn"
              >
                {replacing ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    Reemplazando...
                  </>
                ) : (
                  <>
                    <Replace className="w-4 h-4" />
                    Reemplazar todo ({scope === 'current' ? 'Hoja actual' : 'Todo'})
                  </>
                )}
              </Button>
            </div>
          </div>

          {query.length >= 2 && (
            <div className="flex items-center justify-between text-xs text-slate-500 font-medium px-1">
              <span>
                {loading ? (
                  'Buscando...'
                ) : (
                  <>
                    {totalResults} resultado{totalResults !== 1 ? 's' : ''} en {hojasCount} hoja
                    {hojasCount !== 1 ? 's' : ''}
                  </>
                )}
              </span>
            </div>
          )}

          {/* Resultados */}
          <div className="flex-1 min-h-0">
            <ScrollArea className="h-full pr-2">
              <div className="space-y-2 pb-4">
                {results.map((result, index) => (
                  <div
                    key={`${result.bloque.id}-${index}`}
                    onClick={() => handleResultClick(result)}
                    className="p-3 border border-slate-100 rounded-xl hover:bg-slate-50/80 cursor-pointer transition-colors"
                    data-testid={`search-result-${index}`}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-2">
                        {getFieldIcon(result.matched_field)}
                        <span className="font-medium text-slate-900 text-sm">
                          {result.bloque.materia}
                        </span>
                        {result.bloque.grupo && (
                          <Badge variant="outline" className="text-[10px] py-0 px-1 bg-slate-50 text-slate-600 font-normal">
                            {result.bloque.grupo}
                          </Badge>
                        )}
                      </div>
                      <Badge className={getStatusColor(result.bloque.estado)} variant="outline">
                        {result.score}%
                      </Badge>
                    </div>

                    <div className="space-y-1 text-xs text-slate-500">
                      <div className="flex items-center gap-2">
                        <FileText className="w-3.5 h-3.5 text-slate-400" />
                        <span className="font-medium text-slate-600">{result.hoja}</span>
                        <span>•</span>
                        <span>
                          {result.dia} {result.hora_inicio}-{result.hora_fin}
                        </span>
                      </div>

                      {result.bloque.docente && (
                        <div className="flex items-center gap-2">
                          <User className="w-3.5 h-3.5 text-slate-400" />
                          <span>{result.bloque.docente}</span>
                        </div>
                      )}

                      {result.bloque.aula && (
                        <div className="flex items-center gap-2">
                          <MapPin className="w-3.5 h-3.5 text-slate-400" />
                          <span>{result.bloque.aula}</span>
                        </div>
                      )}

                      {result.matched_value && result.matched_field && (
                        <div className="mt-2 text-[11px] text-blue-600 bg-blue-50/50 px-2 py-0.5 rounded inline-block font-normal">
                          Coincidencia en {result.matched_field}: "{result.matched_value}"
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                {query.length >= 2 && !loading && results.length === 0 && (
                  <div className="text-center py-12 text-slate-400">
                    <Search className="w-10 h-10 mx-auto mb-3 opacity-20" />
                    <p className="font-medium text-slate-600">No se encontraron resultados para "{query}"</p>
                    <p className="text-xs mt-1">Intenta con otros términos de búsqueda</p>
                  </div>
                )}
              </div>
            </ScrollArea>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
};

export default GlobalSearch;
