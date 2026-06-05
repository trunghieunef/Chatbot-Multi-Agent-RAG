FROM node:22-alpine

WORKDIR /app

ARG INTERNAL_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_API_URL=/api/v1
ENV INTERNAL_API_URL=${INTERNAL_API_URL}
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start"]
