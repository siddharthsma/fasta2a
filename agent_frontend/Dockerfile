# Stage 1: Build the React app
FROM node:18-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# Stage 2: Serve with Nginx
FROM nginx:alpine

# Install envsubst for template variable substitution
RUN apk add --no-cache gettext

# Copy built assets from the builder stage
COPY --from=builder /app/build /usr/share/nginx/html

# Copy Nginx config TEMPLATE (not the final file)
COPY nginx.conf.template /etc/nginx/nginx.conf.template

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh

# Ensure script is executable
RUN chmod +x /entrypoint.sh

# Use the entrypoint script
ENTRYPOINT ["/entrypoint.sh"]