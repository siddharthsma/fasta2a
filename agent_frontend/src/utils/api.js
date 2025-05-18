import { v4 as uuidv4 } from 'uuid';
import { API_CONFIG } from '../config';

export const buildSendRequest = (input, sessionId, taskId, metadata) => ({
    jsonrpc: '2.0',
    id: taskId,
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
    
    // Get the latest agent message from artifacts - TODO: Handle multiple artifacts' messages
    const agentMessage = response.result.artifacts[0]?.parts[0]?.text || '';
    
    return {
      messages: [{
        role: 'agent',
        parts: [{ type: 'text', text: agentMessage }],
      }],
      metadata: response.result.metadata
    };
  };

export const truncateTitle = (text, maxLength = 21) => {
  if (text.length <= maxLength) return text;
  return `${text.substring(0, maxLength)}...`;
};

export const buildGetRequest = (taskId) => ({
    jsonrpc: "2.0",
    id: taskId,
    method: "tasks/get",
    params: {
      id: taskId,
      historyLength: 10,
      metadata: {}
    }
  });
  
export const parseGetResponse = (response) => {
    const task = response.result;
    return {
      messages: task.history.map(msg => ({
        ...msg,
        id: uuidv4(),
        status: 'complete',
        timestamp: new Date()
      })),
      sessionId: task.sessionId,
      taskId: task.id,
      metadata: task.metadata
    };
};