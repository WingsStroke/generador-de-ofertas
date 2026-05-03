# PRD - Procesador de Horarios Académicos

## Problema Original
Aplicación web full-stack para extraer, visualizar, corregir y exportar información académica desde archivos XLSX de ofertas universitarias. Frontend interactivo (grid editable, drag & drop, undo/redo) sincronizado con el Excel original. Parser con regex + fuzzy matching (rapidfuzz) contra diccionarios JSON predefinidos. Exportación a JSON.

## Stack
- **Backend**: FastAPI + MongoDB (motor) + openpyxl + rapidfuzz
- **Frontend**: React + Tailwind + Shadcn UI + react-beautiful-dnd
- **Persistencia**: MongoDB (colección `schedules`)
- **Diccionarios**: 4 programas (ingeniería de sistemas, civil, química, alimentos) en `/app/backend/diccionarios/*.json`

## Implementado (estado actual)
- [x] Upload XLSX multi-hoja con selector de programa (`POST /api/upload`)
- [x] Parser robusto: usa filas Excel reales, detecta etiquetas partidas (`"12:00 -"` + `"12:50"`) y filas con rowspan; word-boundary matching (`\b...\b`) para no confundir "HORARIO" con "HORA"
- [x] Parser con detección de múltiples materias/grupos por celda
- [x] Fuzzy matching contra diccionarios académicos (rapidfuzz)
- [x] Cálculo automático de bloques de 50 min (`utils/time_utils.py`)
- [x] Grid editable con tabs por hoja del Excel
- [x] Vista previa del Excel original lado a lado (1:1 con el archivo)
- [x] Drag & drop entre celdas con undo/redo (`HistoryContext`)
- [x] Editor de bloque con autocomplete fuzzy de materias
- [x] Pestaña "Horarios" para agregar/editar/eliminar intervalos de 50 min por bloque
- [x] Búsqueda global cross-hoja (materia/docente/aula)
- [x] Expansión visual cuando una celda tiene múltiples grupos
- [x] **Edición múltiple**: modo selección con checkboxes, FAB "Editar N seleccionados" y dialog para aplicar cambios masivos (materia, grupo, docente, aula) con endpoint `PATCH /api/schedule/{id}/blocks/bulk`
- [x] Update/delete/move/horarios funcionan correctamente en todas las hojas (no solo la primera)
- [x] Exportación JSON multi-hoja
- [x] Persistencia en MongoDB

## Endpoints API
- `GET /api/programs`, `POST /api/upload?program_id={id}`, `GET /api/schedules`, `GET /api/schedule/{id}`
- `PUT /api/schedule/{id}/cell/{dia}/{hora}/block/{block_id}` - actualizar 1 bloque (busca en todas las hojas)
- `DELETE /api/schedule/{id}/cell/{dia}/{hora}/block/{block_id}` - eliminar 1 bloque
- `PATCH /api/schedule/{id}/blocks/bulk` - edición múltiple `{block_ids: [...], update: {...}}`
- `POST /api/schedule/{id}/move-block` - drag & drop
- `PUT /api/schedule/{id}/block/{block_id}/horarios` - actualiza intervalos 50 min
- `POST /api/schedule/{id}/export`, `GET /api/schedule/{id}/search?q=...`
- `GET /api/subjects?program_id=...`, `GET /api/subjects/search/{query}?program_id=...`

## Backlog (P1)
- Validar solapamiento server-side al guardar horarios (helper `validar_solapamiento` ya existe, falta cablear)
- Tipar `horarios` como `List[TimeSlot]` Pydantic en lugar de `List[Dict]`
- Validar valor de `dia` (L/M/X/J/V/S/D) en endpoint horarios
- Usar id estable por intervalo de horario (no índice de array) para mejor reconciliación React
- Mostrar inputs de hora en formato 24h consistente

## Backlog (P2)
- DELETE endpoint para eliminar un schedule completo
- Paginación en `GET /api/schedules` (actualmente `to_list(1000)`)
- Validación MIME real al subir (no solo extensión)
- Mover instanciación de `SubjectMatcher` a singleton de módulo

## Test Reports
- `/app/test_reports/iteration_1.json` - upload, CRUD, autocomplete (13/13)
- `/app/test_reports/iteration_2.json` - feature Horarios + regresión completa (19/19)

## Last update: 2026-02
