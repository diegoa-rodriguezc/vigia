# ── Frontend React de VigIA (build + nginx) ──
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
# La URL del API se inyecta en build (Vite). Por defecto apunta al backend local.
ARG VITE_API_BASE_URL=http://localhost:8080/api/v1
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
