from datetime import datetime, timedelta
from typing import Tuple

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
