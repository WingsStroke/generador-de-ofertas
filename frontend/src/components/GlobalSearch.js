import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Search, X, FileText, MapPin, User, Book } from 'lucide-react';
import { Input } from './ui/input';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { ScrollArea } from './ui/scroll-area';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
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

const GlobalSearch = ({ onNavigate }) => {
  const { scheduleId } = useParams();
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [searchType, setSearchType] = useState('all');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [totalResults, setTotalResults] = useState(0);
  const [hojasCount, setHojasCount] = useState(0);

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
          Buscar
          <kbd className="hidden sm:inline-flex h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium text-muted-foreground opacity-100">
            <span className="text-xs">⌘</span>F
          </kbd>
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="w-full sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>Búsqueda Global</SheetTitle>
          <SheetDescription>
            Busca materias, docentes o aulas en todas las hojas del horario
          </SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-4">
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

          {query.length >= 2 && (
            <div className="flex items-center justify-between text-sm text-slate-600">
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

          <ScrollArea className="h-[calc(100vh-280px)]">
            <div className="space-y-2">
              {results.map((result, index) => (
                <div
                  key={`${result.bloque.id}-${index}`}
                  onClick={() => handleResultClick(result)}
                  className="p-4 border rounded-lg hover:bg-slate-50 cursor-pointer transition-colors"
                  data-testid={`search-result-${index}`}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2">
                      {getFieldIcon(result.matched_field)}
                      <span className="font-medium text-slate-900">
                        {result.bloque.materia}
                      </span>
                      {result.bloque.grupo && (
                        <Badge variant="outline" className="text-xs">
                          {result.bloque.grupo}
                        </Badge>
                      )}
                    </div>
                    <Badge className={getStatusColor(result.bloque.estado)} variant="outline">
                      {result.score}%
                    </Badge>
                  </div>

                  <div className="space-y-1 text-sm text-slate-600">
                    <div className="flex items-center gap-2">
                      <FileText className="w-3 h-3" />
                      <span className="font-medium">{result.hoja}</span>
                      <span>•</span>
                      <span>
                        {result.dia} {result.hora_inicio}-{result.hora_fin}
                      </span>
                    </div>

                    {result.bloque.docente && (
                      <div className="flex items-center gap-2">
                        <User className="w-3 h-3" />
                        <span>{result.bloque.docente}</span>
                      </div>
                    )}

                    {result.bloque.aula && (
                      <div className="flex items-center gap-2">
                        <MapPin className="w-3 h-3" />
                        <span>{result.bloque.aula}</span>
                      </div>
                    )}

                    {result.matched_value && result.matched_field && (
                      <div className="mt-2 text-xs text-blue-600 bg-blue-50 px-2 py-1 rounded inline-block">
                        Coincidencia en: {result.matched_field} "{result.matched_value}"
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {query.length >= 2 && !loading && results.length === 0 && (
                <div className="text-center py-12 text-slate-500">
                  <Search className="w-12 h-12 mx-auto mb-4 opacity-20" />
                  <p>No se encontraron resultados para "{query}"</p>
                  <p className="text-sm mt-2">Intenta con otros términos de búsqueda</p>
                </div>
              )}
            </div>
          </ScrollArea>
        </div>
      </SheetContent>
    </Sheet>
  );
};

export default GlobalSearch;
