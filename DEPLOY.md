# 🚀 Guía de Despliegue - Ubuntu 24.04 + Nginx + Uvicorn

Esta guía te ayuda a desplegar el proyecto en una VM Ubuntu 24 usando Nginx como proxy inverso y Uvicorn como servidor ASGI.

## 📋 Requisitos

- Ubuntu 24.04 LTS
- Acceso SSH a la VM
- Usuario con privilegios sudo
- Puertos disponibles: 80 (Nginx) y 8001 (Backend)

## 🛠️ Paso a Paso

### Paso 1: Conectar a tu VM

```bash
ssh tu-usuario@ip-de-tu-vm
cd ~
```

### Paso 2: Subir el proyecto a la VM

Opción A - Usando SCP (desde tu PC local):
```bash
# En tu PC local (no en la VM)
scp -r Generador-de-ofertas tu-usuario@ip-de-tu-vm:~/
```

Opción B - Usando Git:
```bash
# En la VM
git clone https://github.com/tu-usuario/Generador-de-ofertas.git
cd Generador-de-ofertas
```

### Paso 3: Ejecutar el script de despliegue

```bash
cd ~/Generador-de-ofertas
sudo bash deploy/deploy.sh
```

Este script hará todo automáticamente:
- Instalar Nginx, Node.js, Python
- Configurar el backend en puerto 8001
- Construir el frontend
- Configurar Nginx como proxy inverso
- Crear y iniciar el servicio systemd

### Paso 4: Verificar el despliegue

```bash
# Verificar que el backend esté corriendo
sudo systemctl status horarios-backend

# Verificar Nginx
sudo systemctl status nginx

# Ver logs en tiempo real
sudo journalctl -u horarios-backend -f
```

### Paso 5: Acceder a la aplicación

Abre tu navegador y visita:
```
http://IP-DE-TU-VM
```

## 🔧 Configuración Manual (Si el script falla)

### 1. Instalar dependencias
```bash
sudo apt update
sudo apt install -y nginx nodejs npm python3 python3-venv
```

### 2. Configurar Backend
```bash
cd /var/www/horarios/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install uvicorn uvloop h11
```

### 3. Iniciar backend manualmente
```bash
cd /var/www/horarios/backend
source venv/bin/activate
uvicorn server:app --host 127.0.0.1 --port 8001 --workers 2
```

### 4. Configurar Frontend
```bash
cd /var/www/horarios/frontend
npm ci
npm run build
```

### 5. Configurar Nginx
Copiar el archivo `deploy/nginx/horarios.conf` a `/etc/nginx/sites-available/horarios`

```bash
sudo ln -s /etc/nginx/sites-available/horarios /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

## 🔒 Habilitar HTTPS (SSL)

```bash
# Instalar Certbot
sudo apt install -y certbot python3-certbot-nginx

# Obtener certificado (reemplaza con tu dominio)
sudo certbot --nginx -d tu-dominio.com

# Verificar auto-renovación
sudo systemctl status certbot.timer
```

## 📝 Cambiar el Puerto (si 8001 también está ocupado)

1. Editar el servicio systemd:
```bash
sudo nano /etc/systemd/system/horarios-backend.service
```

2. Cambiar `--port 8001` por el puerto que quieras (ej: 8002)

3. Recargar y reiniciar:
```bash
sudo systemctl daemon-reload
sudo systemctl restart horarios-backend
```

4. Actualizar Nginx:
```bash
sudo nano /etc/nginx/sites-available/horarios
# Cambiar proxy_pass http://127.0.0.1:8001/ por el nuevo puerto
sudo nginx -t
sudo systemctl restart nginx
```

## 🐛 Solución de Problemas

### Error: "Address already in use" (Puerto 8001 ocupado)
```bash
# Encontrar proceso usando el puerto
sudo lsof -i :8001

# Matar el proceso
sudo kill -9 <PID>

# O cambiar a otro puerto siguiendo los pasos de arriba
```

### Error: "Permission denied" en Nginx
```bash
sudo chown -R www-data:www-data /var/www/horarios
sudo chmod -R 755 /var/www/horarios
```

### Backend no inicia
```bash
# Ver logs detallados
sudo journalctl -u horarios-backend -n 50 --no-pager

# Probar manualmente
cd /var/www/horarios/backend
source venv/bin/activate
uvicorn server:app --host 127.0.0.1 --port 8001 --reload
```

## 📊 Comandos Útiles

```bash
# Ver estado de todo
sudo systemctl status nginx
sudo systemctl status horarios-backend

# Ver logs en tiempo real
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
sudo journalctl -u horarios-backend -f

# Restart servicios
sudo systemctl restart nginx
sudo systemctl restart horarios-backend

# Ver puertos en uso
sudo netstat -tlnp | grep -E ':(80|8001)'
```

## 🔄 Actualizar el código

```bash
cd ~/Generador-de-ofertas

# Actualizar código (git pull o scp nuevos archivos)
git pull origin main

# Reconstruir frontend
cd frontend
npm ci
npm run build
sudo cp -r build /var/www/horarios/frontend/

# Reiniciar servicios
sudo systemctl restart horarios-backend
sudo systemctl restart nginx
```

## 📞 Soporte

Si tienes problemas, revisa:
1. Logs de Nginx: `sudo tail -f /var/log/nginx/error.log`
2. Logs del backend: `sudo journalctl -u horarios-backend -f`
3. Verifica que los puertos estén abiertos: `sudo ufw status`
