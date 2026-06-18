# Backend FastAPI — à builder avec le contexte = RACINE du repo (voir compose.yml),
# car il importe les packages métier (core/, generation/, processing/, sessions/).
FROM python:3.12-slim

# Proxy DGFIP (réseau interne) — adapter/retirer hors intranet.
ENV HTTP_PROXY='http://proxy.infra.dgfip:3128'
ENV HTTPS_PROXY='http://proxy.infra.dgfip:3128'
ENV NO_PROXY='localhost,127.0.0.1,*.rie.gouv.fr'

# Dépendances système nécessaires au traitement documentaire (PyMuPDF, ODF, PPTX...).
RUN apt-get update && apt-get install -y \
    libgl1 libglib2.0-0 libgomp1 curl \
    libreoffice-core libreoffice-writer libreoffice-impress libreoffice-calc \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dépendances métier (racine) + couche web (backend).
COPY requirements.txt ./requirements.txt
COPY backend/requirements.txt ./backend-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r backend-requirements.txt

COPY . .

RUN mkdir -p /app/shared_data

EXPOSE 8000

# --root-path = préfixe public de l'API (le reverse-proxy retire ce préfixe) :
# nécessaire pour que Swagger /quizzator-back/docs charge sa spec.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--root-path", "/quizzator-back"]
