FROM node:24-slim

WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

# Dependencies sit in their own layer: editing source does not reinstall them.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
# Type errors fail here, when the image is built, not when a page is first opened.
RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start"]
