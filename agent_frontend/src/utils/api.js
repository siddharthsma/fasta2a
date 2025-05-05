import { v4 as uuidv4 } from 'uuid';
import { API_CONFIG } from '../config';

export const buildSendRequest = (input, sessionId, metadata) => ({
  jsonrpc: '2.0',
  id: 1, // You might want to make this dynamic
  method: API_CONFIG.METHODS.SEND,
  params: {
    id: sessionId,
    sessionId,
    message: {
      role: 'user',
      parts: [{
        type: 'text',
        text: input
      }]
    },
    metadata
  }
});

export const parseSendResponse = (response) => {
  if (!response.result) throw new Error('Invalid response format');
  
  return {
    messages: response.result.history.map(item => ({
      role: item.role,
      parts: item.parts,
      timestamp: new Date()
    })),
    metadata: response.result.metadata
  };
};

export const truncateTitle = (text, maxLength = 50) => {
  if (text.length <= maxLength) return text;
  return `${text.substring(0, maxLength)}...`;
};