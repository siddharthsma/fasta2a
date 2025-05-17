#!/bin/sh

# Generate nginx.conf from template
envsubst '${SERVER_URL} ${NATS_WS_URL}' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf

# Generate runtime configuration using environment variables
cat <<EOF > /usr/share/nginx/html/config.js
window.APP_CONFIG = {
  SERVER_URL: "${SERVER_URL}",
  NATS_WS_URL: "${NATS_WS_URL}"
};
EOF

# Start Nginx
exec nginx -g 'daemon off;'