FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Public, browser-visible values only. Never pass a secret as a VITE_ variable.
ARG VITE_API_URL=""
ARG VITE_AG_LICENSE_KEY=""
ENV VITE_API_URL=$VITE_API_URL VITE_AG_LICENSE_KEY=$VITE_AG_LICENSE_KEY
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
