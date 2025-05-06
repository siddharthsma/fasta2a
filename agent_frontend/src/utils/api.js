import { v4 as uuidv4 } from 'uuid';
import { API_CONFIG } from '../config';

export const buildSendRequest = (input, sessionId, taskId, metadata) => ({
    jsonrpc: '2.0',
    id: 1,
    method: 'tasks/send',
    params: {
      id: taskId,       // Should come from currentTaskId
      sessionId: sessionId,
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
    
    // Get the latest agent message from artifacts
    const agentMessage = response.result.artifacts[0]?.parts[0]?.text || '';
    
    return {
      messages: [{
        role: 'agent',
        parts: [{ type: 'text', text: agentMessage }],
      }],
      metadata: response.result.metadata
    };
  };

export const truncateTitle = (text, maxLength = 50) => {
  if (text.length <= maxLength) return text;
  return `${text.substring(0, maxLength)}...`;
};


export const buildGetRequest = (taskId) => ({
    jsonrpc: '2.0',
    id: uuidv4(),
    method: 'tasks/get',
    params: {
      id: taskId
    }
  });
  
  export const parseGetResponse = (response) => {
    if (!response.result) throw new Error('Invalid response format');
    
    return {
      messages: response.result.history.map(item => ({
        role: item.role,
        parts: item.parts,
        timestamp: new Date()
      })),
      metadata: response.result.metadata,
      sessionId: response.result.sessionId,
      taskId: response.result.id
    };
  };