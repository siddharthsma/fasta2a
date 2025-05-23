import { v4 as uuidv4 } from 'uuid';
import { API_CONFIG } from '../config';

export const buildSendRequest = (input, files, sessionId, taskId, metadata) => {
  // Create message parts array
  const parts = [];
  
  // Add text part if input exists
  if (input.trim()) {
    parts.push({
      type: 'text',
      text: input
    });
  }

  // Add file parts
  if (files?.length > 0) {
    files.forEach(file => {
      parts.push({
        type: 'file',
        file: {
          name: file.name,
          mimeType: file.type,
          bytes: file.base64 // We'll need to convert files to base64
        }
      });
    });
  }

  return {
    jsonrpc: '2.0',
    id: taskId,
    method: 'tasks/send',
    params: {
      id: taskId,
      sessionId: sessionId,
      message: {
        role: 'user',
        parts: parts,
      },
      metadata: metadata || {}
    }
  };
};

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