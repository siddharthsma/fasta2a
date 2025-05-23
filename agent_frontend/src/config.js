const API_CONFIG = {
    SERVER_URL: window.APP_CONFIG?.SERVER_URL || "http://localhost:8001",
    NATS_WS_URL: window.APP_CONFIG?.NATS_WS_URL || "ws://localhost:9222"
};
export default API_CONFIG;