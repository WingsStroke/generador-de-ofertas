from datetime import datetime, timedelta
from typing import Tuple, Optional, List

# ---------------------------------------------------------------------------
# Formato académico FIJO de la universidad (jornada diurna: 7:00 AM - 6:00 PM).
# Cada bloque equivale a 50 minutos, con un receso de 10 minutos entre el
# bloque de las 12:00-12:50 y el de la 1:00-1:50 PM.
#
# Este formato NUNCA se extrae de los archivos subidos: es constante para
# toda la aplicación. Los archivos solo se usan para ubicar en qué fila vive
# cada bloque dentro de una tabla concreta; la hora final que se asigna a esa
# fila siempre es una de estas 13, nunca un valor "inventado" por el archivo.
# ---------------------------------------------------------------------------
UNIVERSITY_SCHEDULE_BLOCKS: List[Tuple[str, str]] = [
    ("07:00", "07:50"),
    ("07:50", "08:40"),
    ("08:40", "09:30"),
    ("09:30", "10:20"),
    ("10:20", "11:10"),
    ("11:10", "12:00"),
    ("12:00", "12:50"),
    ("13:00", "13:50"),
    ("13:50", "14:40"),
    ("14:40", "15:30"),
    ("15:30", "16:20"),
    ("16:20", "17:10"),
    ("17:10", "18:00"),
]


def _hora_a_minutos(hora: str) -> Optional[int]:
    """Convierte 'HH:MM' a minutos desde medianoche. None si no es válido."""
    try:
        h, m = map(int, hora.strip().split(":"))
        return h * 60 + m
    except Exception:
        return None


def _normalizar_hora_diurna(hora_str: str) -> Optional[int]:
    """
    Interpreta una hora tal como suele aparecer en los archivos subidos, donde
    normalmente NO se indica AM/PM de forma explícita (ej. '1:00' en vez de
    '13:00' o '1:00 PM'). Como la jornada diurna de la universidad nunca
    inicia antes de las 7:00 AM, cualquier hora con dígito de la 1 a las 6
    corresponde inequívocamente a la tarde (13:00-18:00).
    """
    minutos = _hora_a_minutos(hora_str)
    if minutos is None:
        return None
    hora = minutos // 60
    if 1 <= hora <= 6:
        minutos += 12 * 60
    return minutos


def snap_to_university_block(hora_inicio_detectada: str, tolerancia_min: int = 25) -> Optional[Tuple[str, str]]:
    """
    Ancla una hora de inicio detectada en un archivo subido al bloque
    académico oficial más cercano de UNIVERSITY_SCHEDULE_BLOCKS.

    Devuelve (inicio, fin) del bloque oficial más cercano si está dentro de
    la tolerancia, o None si no hay ningún bloque suficientemente cercano
    (en cuyo caso el llamador debe descartar la fila en vez de inventar un
    bloque nuevo).
    """
    minutos = _normalizar_hora_diurna(hora_inicio_detectada)
    if minutos is None:
        return None

    mejor_bloque = None
    mejor_diff = None
    for inicio, fin in UNIVERSITY_SCHEDULE_BLOCKS:
        bloque_min = _hora_a_minutos(inicio)
        diff = abs(minutos - bloque_min)
        if mejor_diff is None or diff < mejor_diff:
            mejor_diff = diff
            mejor_bloque = (inicio, fin)

    if mejor_bloque is not None and mejor_diff <= tolerancia_min:
        return mejor_bloque
    return None


def calcular_bloques_horarios(hora_inicio: str, hora_fin: str) -> Tuple[int, int]:
    """
    Calcula el número de bloques de 50 minutos entre dos horas
    
    Returns:
        (numero_bloques, minutos_totales)
    """
    try:
        inicio = datetime.strptime(hora_inicio, "%H:%M")
        fin = datetime.strptime(hora_fin, "%H:%M")
        
        if fin <= inicio:
            fin += timedelta(days=1)
        
        diferencia = fin - inicio
        minutos_totales = int(diferencia.total_seconds() / 60)
        
        bloques = minutos_totales // 50
        
        return (bloques, minutos_totales)
    except:
        return (0, 0)

def validar_solapamiento(horarios_existentes: list, nuevo_horario: dict) -> bool:
    """
    Valida si un nuevo horario se solapa con horarios existentes
    
    Returns:
        True si hay solapamiento, False si no hay conflicto
    """
    nuevo_dia = nuevo_horario["dia"]
    nuevo_inicio = datetime.strptime(nuevo_horario["hora_inicio"], "%H:%M")
    nuevo_fin = datetime.strptime(nuevo_horario["hora_fin"], "%H:%M")
    
    for horario in horarios_existentes:
        if horario["dia"] != nuevo_dia:
            continue
        
        existente_inicio = datetime.strptime(horario["hora_inicio"], "%H:%M")
        existente_fin = datetime.strptime(horario["hora_fin"], "%H:%M")
        
        if (nuevo_inicio < existente_fin and nuevo_fin > existente_inicio):
            return True
    
    return False

def formatear_duracion(minutos: int) -> str:
    """
    Formatea minutos en texto legible
    """
    horas = minutos // 60
    mins = minutos % 60
    
    if horas > 0 and mins > 0:
        return f"{horas}h {mins}min"
    elif horas > 0:
        return f"{horas}h"
    else:
        return f"{mins}min"
