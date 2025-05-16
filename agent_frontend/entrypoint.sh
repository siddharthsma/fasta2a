#!/bin/sh

# Generate runtime configuration using environment variables
cat <<EOF > /usr/share/nginx/html/config.js
window.APP_CONFIG = {
  SERVER_URL: "${SERVER_URL}",
  NATS_URL: "${NATS_URL}"
};
EOF

# Start Nginx
exec nginx -g 'daemon off;'