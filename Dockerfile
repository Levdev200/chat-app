# Imagen base
FROM python:3.11-slim

# Crear carpeta de trabajo
WORKDIR /app

# Copiar dependencias
COPY requirements.txt ./

# Instalar dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Exponer puertos HTTP y WebSocket
EXPOSE 80 8000

# Comando de inicio
CMD ["python", "server.py"]
