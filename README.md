# Validador de Horarios Académicos

Sistema completo para extracción, visualización, corrección y exportación de información académica desde archivos XLSX de ofertas académicas universitarias.

## Características Principales

### Múltiples Programas Académicos
- **Soporte para 4 carreras de ingeniería**: Sistemas (66 materias), Alimentos (68), Civil (69), Química (66)
- **Selector de programa**: Elige el programa antes de subir el archivo
- **Diccionarios específicos**: Cada programa tiene su propio diccionario de materias
- **Fuzzy matching contextual**: Búsqueda de materias según el programa seleccionado
- **Extensible**: Agregar nuevos programas es tan simple como añadir un archivo JSON

### Procesamiento Automático
- **Lectura de Excel**: Procesa archivos XLSX con formato calendario (días como columnas, horas como filas)
- **Extracción inteligente**: Identifica materias, grupos, docentes y aulas usando expresiones regulares y parsing semántico
- **Fuzzy Matching**: Coincide materias con el diccionario académico usando rapidfuzz
- **Detección de grupos**: Patrón fuerte [A-Z][0-9]+ (ej: A1, B2, C3)
- **Múltiples clases por celda**: Divide automáticamente celdas con varias clases

### Dashboard Interactivo
- **Panel dual sincronizado**:
  - Izquierda: Grid editable del horario procesado
  - Derecha: Vista del archivo Excel original
- **Sistema de pestañas**: Navegación entre todas las hojas/semestres del Excel
- **Estados visuales**: Confirmado (verde), Inferido (amarillo), Error (rojo), Desconocido (gris)
- **Sincronización**: Al seleccionar una celda se resalta en ambos paneles
- **Múltiples bloques**: Botón "+N más" para expandir/colapsar celdas con varios grupos
- **Historial Undo/Redo**: Ctrl+Z para deshacer, Ctrl+Shift+Z para rehacer
- **Indicador de cambios**: Badge "Sin guardar" cuando hay modificaciones pendientes

### Editor de Bloques
- **Edición estructurada**: Modifica materia, grupo, docente y aula
- **Autocompletado inteligente**: Sugerencias con fuzzy matching del diccionario
- **Validación en tiempo real**: Nivel de confianza y estado visual
- **Operaciones**: Editar, guardar, eliminar bloques
- **Drag & Drop**: Arrastra bloques entre celdas para reorganizar horarios
- **Expansión de celdas**: Ver todos los grupos cuando hay múltiples en misma celda

### Exportación
- **Formato JSON estructurado**: Compatible con el formato especificado
- **Multi-hoja**: Exporta datos de todas las hojas/semestres en un solo archivo
- **Metadatos completos**: Versión, programa, fecha, totales por hoja
- **Organización jerárquica**: Hojas → Semestres → Asignaturas → Grupos → Horarios

## Tecnologías

### Backend
- **FastAPI**: Framework web moderno
- **openpyxl**: Lectura de archivos Excel
- **rapidfuzz**: Fuzzy matching para materias
- **MongoDB**: Almacenamiento de horarios procesados
- **Pydantic**: Validación de datos

### Frontend
- **React 19**: Interfaz de usuario
- **Tailwind CSS**: Diseño minimalista y responsivo
- **shadcn/ui**: Componentes UI accesibles
- **Axios**: Comunicación con API
- **React Router**: Navegación

## Estructura del Proyecto

```
/app/
├── backend/
│   ├── server.py                    # API principal
│   ├── models.py                    # Modelos Pydantic
│   ├── utils/
│   │   ├── excel_reader.py          # Lectura Excel
│   │   ├── text_cleaner.py          # Limpieza de texto
│   │   ├── semantic_parser.py       # Extracción de entidades
│   │   ├── subject_matcher.py       # Fuzzy matching
│   │   ├── schedule_processor.py    # Procesador principal
│   │   └── export_helper.py         # Exportación JSON
│   └── diccionario_ingenieria_de_sistemas.json
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Upload.js            # Página de carga
│       │   └── Dashboard.js         # Dashboard principal
│       ├── components/
│       │   ├── ScheduleGrid.js      # Grid del horario
│       │   ├── ExcelPreview.js      # Vista Excel original
│       │   └── BlockEditor.js       # Editor de bloques
│       └── context/
│           └── ScheduleContext.js   # Estado global
```

## API Endpoints

### Programas Académicos
- `GET /api/programs` - Listar programas disponibles

### Procesamiento
- `POST /api/upload?program_id={id}` - Subir y procesar archivo XLSX con programa específico
- `GET /api/schedules` - Listar todos los horarios
- `GET /api/schedule/{id}` - Obtener horario específico

### Edición
- `PUT /api/schedule/{id}/cell/{dia}/{hora}/block/{block_id}` - Actualizar bloque
- `DELETE /api/schedule/{id}/cell/{dia}/{hora}/block/{block_id}` - Eliminar bloque

### Exportación
- `POST /api/schedule/{id}/export` - Exportar a formato JSON

### Diccionario
- `GET /api/subjects?program_id={id}` - Obtener materias de un programa
- `GET /api/subjects/search/{query}?program_id={id}` - Buscar con fuzzy matching

## Métricas de Confianza

El sistema calcula niveles de confianza para cada bloque:
- **≥ 90%**: Estado confirmado (verde)
- **70-89%**: Estado inferido (amarillo)
- **< 70%**: Estado desconocido (gris)
- **Sin grupo detectado**: Reduce confianza en 20%

## Diccionarios Académicos

El sistema incluye 4 programas de ingeniería con sus respectivos planes de estudio:

### Ingeniería de Sistemas (66 materias)
- Matemáticas y ciencias básicas: Cálculo, Álgebra, Estadística, Física
- Programación y desarrollo: Algoritmos, POO, Estructuras de Datos, Desarrollo Web
- Redes y telecomunicaciones: Redes, Sistemas Distribuidos, Seguridad
- Bases de datos y sistemas: BD, Arquitectura de Software, Sistemas Operativos
- Inteligencia artificial: Machine Learning, Procesamiento de Lenguaje Natural

### Ingeniería de Alimentos (68 materias)
- Ciencias básicas: Química General, Orgánica, Analítica, Bioquímica
- Microbiología: Microbiología General y de Alimentos
- Procesos: Ingeniería de Procesos, Operaciones Unitarias
- Tecnología de alimentos: Conservación, Procesamiento, Control de Calidad
- Nutrición y análisis: Bromatología, Análisis de Alimentos

### Ingeniería Civil (69 materias)
- Matemáticas y física: Cálculo, Mecánica, Resistencia de Materiales
- Estructuras: Análisis Estructural, Diseño de Estructuras
- Materiales: Materiales de Construcción, Tecnología del Concreto
- Geotecnia: Mecánica de Suelos, Cimentaciones
- Hidráulica: Hidráulica, Acueductos, Alcantarillado

### Ingeniería Química (66 materias)
- Química fundamental: Química General, Orgánica, Analítica, Fisicoquímica
- Termodinámica: Termodinámica General, Aplicada
- Procesos: Balance de Materia y Energía, Operaciones Unitarias
- Reactores: Cinética, Diseño de Reactores
- Control: Instrumentación, Control de Procesos

## Diccionario Académico

El sistema incluye el plan de estudios de Ingeniería de Sistemas con:
- Nombre oficial de cada asignatura
- Código de la materia
- Número de créditos

El fuzzy matching permite identificar materias incluso con:
- Errores de tipeo
- Abreviaturas
- Variaciones en el nombre

### Agregar Nuevos Programas

Para agregar un nuevo programa académico:

1. Crear archivo JSON en `/app/backend/diccionarios/{programa_id}.json`
2. Estructura del diccionario:
```json
{
  "materia_id": {
    "nombre_oficial": "Nombre de la Materia",
    "codigo": "CODIGO",
    "creditos": 3
  }
}
```
3. Reiniciar el backend - el programa se cargará automáticamente
4. El nuevo programa aparecerá en el selector de la página de upload

## Formato de Exportación

```json
{
  "metadata": {
    "programa": "Ingeniería de Sistemas",
    "archivo": "horario.xlsx",
    "fechaProcesamiento": "2026-05-01T...",
    "totalAsignaturas": 82,
    "totalGrupos": 106,
    "version": "2.0.0"
  },
  "semestres": [
    {
      "numero": 1,
      "asignaturas": [
        {
          "id": "calculo_diferencial",
          "nombre": "Cálculo Diferencial",
          "creditos": 3,
          "grupos": [
            {
              "id": "calculo_diferencial_a1",
              "grupo": "A1",
              "profesor": "...",
              "ubicacion": "...",
              "horarios": [
                {
                  "dia": "L",
                  "inicio": "10:20",
                  "fin": "12:00",
                  "jornada": "diurna"
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

## Pruebas

El sistema ha sido probado exhaustivamente:
- ✅ 13/13 tests backend (100%)
- ✅ Tests E2E frontend (95%)
- ✅ Procesamiento de archivo real: ~80% de confianza
- ✅ 34 celdas procesadas, 29 bloques con grupo detectado
- ✅ 25 bloques confirmados

## Diseño

Siguiendo las directrices del usuario:
- **Estilo**: Sencillo, moderno y minimalista
- **Colores**: Claros, sin complejidad
- **Tipografía**: Outfit (headings), Manrope (body)
- **Paleta**: Blanco, slate, azul para acciones
- **Indicadores semánticos**: Verde, amarillo, rojo para estados

## Escalabilidad

El sistema está diseñado para:
- Múltiples formatos de entrada Excel
- Diferentes carreras y programas académicos
- Evolución del diccionario académico
- Separación completa entre lógica de parsing y frontend
