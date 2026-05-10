#!/bin/bash
set -e

# ============================================
# Script de Despliegue - Horarios Académicos
# Ubuntu 24.04 LTS + Nginx + Uvicorn (Puerto 8001)
# ============================================

PROJECT_NAME="horarios"
PROJECT_DIR="/var/www/${PROJECT_NAME}"
BACKEND_DIR="${PROJECT_DIR}/backend"
FRONTEND_DIR="${PROJECT_DIR}/frontend"
NGINX_CONF="/etc/nginx/sites-available/${PROJECT_NAME}"

echo "🚀 Iniciando despliegue de Horarios Académicos..."
echo "📌 Puerto del backend: 8001 (8000 está ocupado)"

# Verificar que se ejecute como root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Este script debe ejecutarse con sudo"
    exit 1
fi

# 1. Instalar dependencias del sistema
echo "📦 Instalando dependencias del sistema..."
apt update
apt install -y nginx nodejs npm python3 python3-pip python3-venv python3-full git curl

# 2. Crear estructura de directorios
echo "📁 Creando directorios en ${PROJECT_DIR}..."
mkdir -p ${PROJECT_DIR}
mkdir -p /var/log/${PROJECT_NAME}

# 3. Copiar archivos del proyecto (asumiendo que estás en el directorio del proyecto)
echo "📂 Copiando archivos del proyecto..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(dirname "$SCRIPT_DIR")"

cp -r "${SOURCE_DIR}/backend" ${PROJECT_DIR}/
cp -r "${SOURCE_DIR}/frontend" ${PROJECT_DIR}/

# 4. Configurar Backend
echo "🔧 Configurando Backend..."
cd ${BACKEND_DIR}

# Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install --upgrade pip
pip install -r requirements.txt
pip install uvicorn uvloop h11

# Crear archivo .env para producción
cat > .env << EOF
REACT_APP_BACKEND_URL=http://localhost
FRONTEND_URL=http://localhost
EOF

# 5. Configurar Frontend
echo "🎨 Construyendo Frontend..."
cd ${FRONTEND_DIR}

# Instalar dependencias y construir
npm ci  # Usa package-lock.json para instalación reproducible
npm run build

# 6. Configurar permisos
echo "🔐 Configurando permisos..."
chown -R www-data:www-data ${PROJECT_DIR}
chmod -R 755 ${PROJECT_DIR}

# 7. Configurar Nginx
echo "🌐 Configurando Nginx..."
cp "${SCRIPT_DIR}/nginx/horarios.conf" ${NGINX_CONF}

# Crear enlace simbólico si no existe
if [ ! -f "/etc/nginx/sites-enabled/${PROJECT_NAME}" ]; then
    ln -s ${NGINX_CONF} /etc/nginx/sites-enabled/${PROJECT_NAME}
fi

# Remover default si existe (opcional)
rm -f /etc/nginx/sites-enabled/default

# Testear configuración de Nginx
echo "🧪 Probando configuración de Nginx..."
nginx -t

# 8. Configurar Systemd
echo "⚙️ Configurando servicio Systemd..."
cp "${SCRIPT_DIR}/systemd/horarios-backend.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable horarios-backend

# 9. Iniciar servicios
echo "🚀 Iniciando servicios..."
systemctl restart nginx
systemctl start horarios-backend

# 10. Verificar estado
echo ""
echo "=========================================="
echo "✅ Despliegue completado!"
echo "=========================================="
echo ""
echo "🌐 Accede a tu aplicación:"
echo "   http://$(hostname -I | awk '{print $1}')"
echo ""
echo "📊 Estado de los servicios:"
systemctl is-active --quiet nginx && echo "   ✅ Nginx: Activo" || echo "   ❌ Nginx: Inactivo"
systemctl is-active --quiet horarios-backend && echo "   ✅ Backend: Activo (puerto 8001)" || echo "   ❌ Backend: Inactivo"
echo ""
echo "📋 Comandos útiles:"
echo "   Ver logs backend:   sudo journalctl -u horarios-backend -f"
echo "   Restart backend:    sudo systemctl restart horarios-backend"
echo "   Ver estado:         sudo systemctl status horarios-backend"
echo "   Ver errores Nginx:  sudo tail -f /var/log/nginx/error.log"
echo ""
echo "🔧 Si necesitas cambiar el puerto:"
echo "   1. Edita:   sudo nano /etc/systemd/system/horarios-backend.service"
echo "   2. Cambia:  --port 8001 por otro puerto"
echo "   3. Recarga: sudo systemctl daemon-reload && sudo systemctl restart horarios-backend"
echo "   4. Actualiza Nginx: sudo nano /etc/nginx/sites-available/horarios"
echo ""
