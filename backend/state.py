from slowapi import Limiter
from slowapi.util import get_remote_address

# Inicializar rate limiter
limiter = Limiter(key_func=get_remote_address)

# Caché global en memoria
programas_dict = {}
processors = {}
