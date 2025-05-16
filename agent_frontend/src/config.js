const API_CONFIG = {
    SERVER_URL: window.APP_CONFIG?.SERVER_URL || "http://localhost:8000",
    NATS_URL: window.APP_CONFIG?.NATS_URL || "ws://localhost:9222"
};
export default API_CONFIG;