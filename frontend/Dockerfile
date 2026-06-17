# Frontend Vue — build multi-stage puis nginx. Décommentez « # DGFIP » sur l'intranet.
FROM node:22-alpine AS builder
# DGFIP: FROM nexus3-docker-pull.appli.dgfip/node:22-alpine AS builder

WORKDIR /app
COPY . .

RUN npm install
# DGFIP: RUN npm config set registry https://nexus3.appli.dgfip/repository/npm-all/ \
#     && npm config set strict-ssl false && npm install
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/quizz
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
