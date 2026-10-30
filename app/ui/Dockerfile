# ---------- Build React / Vite app ----------
FROM node:20-alpine AS vite-app

WORKDIR /app

COPY package*.json ./
RUN rm -f package-lock.json
RUN npm install

COPY . .
RUN npm run build

# ---------- Nginx stage ----------
FROM nginx:alpine

# Copy nginx server template (NOT nginx.conf!)
COPY ./nginx.conf /etc/nginx/templates/default.conf.template

# Copy built frontend
COPY --from=vite-app /app/dist /usr/share/nginx/html

EXPOSE 80

# DO NOT override entrypoint — nginx image needs it for envsubst
CMD ["nginx", "-g", "daemon off;"]
