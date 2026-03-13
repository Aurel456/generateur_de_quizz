# Utilisez une image Python officielle comme base
FROM python:3.12-slim

ENV HTTP_PROXY='http://proxy.infra.dgfip:3128'
ENV HTTPS_PROXY='http://proxy.infra.dgfip:3128'
ENV NO_PROXY='localhost,10.156.253.10,100.70.1.199,10.125.47.87,*.rie.gouv.fr,web.assistant-ia-gen-dev-webapp.dgfip.nuage01.fi.francecloud.rie.gouv.fr,forge.dgfip.finances.rie.gouv.fr,pia-exp-back.dev.dgfip,100.70.1.199,forge.dgfip.finances.rie.gouv.fr,nexus-cloud.appli.dgfip'

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Définissez le répertoire de travail dans le conteneur
WORKDIR /app

# Copiez les requirements dans le conteneur
COPY requirements.txt .

# S'il faut des librairies supplémentaires niveau système d'exploitation
# RUN apt-get update && apt-get install -y libpq-dev poppler-utils libgl1 libglib2.0-0

# Installez les dépendances
RUN pip install -r requirements.txt

# Copiez l'application et les secrets dans le conteneur
# COPY app.py .
# COPY .streamlit/secrets.toml .streamlit/secrets.toml
# Pour copier tous les fichiers du repo dans le conteneur
COPY . . 

RUN mkdir -p /app/shared_data


# Exposez le port que Streamlit utilisera
EXPOSE 8501

# Démarrez Streamlit lorsque le conteneur est lancé
CMD ["streamlit", "run", "app.py"]

