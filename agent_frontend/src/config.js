const API_CONFIG = {
    BASE_URL: window.APP_CONFIG?.BASE_URL || "http://localhost:8000",
    NATS_URL: window.APP_CONFIG?.NATS_URL || "ws://localhost:9222",
    METHODS: {
        SEND: 'tasks/send'
      }
};
export default API_CONFIG;