# ---------- Сборка ----------
FROM node:22-alpine AS build
WORKDIR /app

COPY package*.json ./

COPY . .

ARG VITE_USE_MOCK=false
ARG VITE_API_URL=/
ENV VITE_USE_MOCK=$VITE_USE_MOCK \
    VITE_API_URL=$VITE_API_URL
RUN npm install
RUN npm run build

# ---------- Раздача ----------
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
CMD ["npx", "vite", "preview", "--host", "0.0.0.0", "--port", "80", "--strictPort"]
