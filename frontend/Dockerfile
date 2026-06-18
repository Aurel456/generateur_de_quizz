# Frontend Vue — build multi-stage puis nginx. Décommentez « # DGFIP » sur l'intranet.
FROM node:22-alpine AS builder
# DGFIP: FROM nexus3-docker-pull.appli.dgfip/node:22-alpine AS builder

WORKDIR /app

# DGFIP: registre nexus interne pour le CLIR (décommenter sur l'intranet).
# RUN npm config set registry https://nexus3.appli.dgfip/repository/npmjs_group/ \
#     && npm config set strict-ssl false

# Installation reproductible depuis le package-lock.json COMMITTÉ.
# npm ci installe EXACTEMENT les versions du lock (présentes dans le miroir nexus figé) ;
# npm install chercherait du plus récent -> 404. Voir docs/MIGRATION_DSFR / template.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine
# DGFIP: FROM nexus3-docker-pull.appli.dgfip/nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/quizzator
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
