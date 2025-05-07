import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { v4 as uuidv4 } from 'uuid';
import { API_CONFIG } from './config';
import { buildSendRequest, parseSendResponse, truncateTitle, parseGetResponse } from './utils/api';
import './App.css';

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [chats, setChats] = useState([]);
  const [activeChat, setActiveChat] = useState(null);
  const [isInitialState, setIsInitialState] = useState(true);
  const [mode, setMode] = useState('send');
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [currentTaskId, setCurrentTaskId] = useState(null);

  const handleNewChat = () => {
    setCurrentSessionId(null);
    setMessages([]);
    setIsInitialState(true);
    setActiveChat(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    setInput(''); // Clear IMMEDIATELY here

    let tempAgentMessage;
  
    try {
      let sessionId   = currentSessionId;
      let taskId      = currentTaskId;   // ← declared in the outer scope
      let metadata    = {};
      let isNewSession = false;

       // Create new chat session if needed
       if (!sessionId) {
        isNewSession = true;
        sessionId = uuidv4();
        taskId = uuidv4(); // Generate separate task ID
        metadata.title = truncateTitle(input);

        setCurrentSessionId(sessionId);
        setCurrentTaskId(taskId); // Set the new task ID
      }

      const userMessage = {
        id: Date.now(),
        role: 'user',
        parts: [{ type: 'text', text: input }],
        status: 'complete',
        timestamp: new Date()
      };
  
      // Add user message immediately
      setMessages(prev => [...prev, userMessage]);
      
      // Add temporary loading message
      tempAgentMessage = {
        id: `temp-${Date.now()}`,
        role: 'agent',
        parts: [{ type: 'text', text: '' }],
        status: 'pending',
        timestamp: new Date()
      };

      setMessages(prev => [...prev, tempAgentMessage]);
      setIsInitialState(false);
  
      // Build and send request
      const requestBody = buildSendRequest(
        input,
        sessionId,
        taskId,
        metadata
      );

      const response = await fetch(API_CONFIG.BASE_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
      });
  
      if (!response.ok) throw new Error('Network response was not ok');
      const responseData = await response.json();
      
      // Parse response and update messages
      const { messages: parsedMessages } = parseSendResponse(responseData);
  
      setMessages(prev => prev.map(msg => {
        if (msg.id === tempAgentMessage.id) {
          return {
            ...msg,
            ...parsedMessages[0],
            id: uuidv4(), // Replace temp ID
            status: 'complete',
            timestamp: new Date()
          };
        }
        return msg;
      }));
  
      // Update chats list if new session
      if (isNewSession) {
        const newChat = {
          id: currentTaskId, // Use task ID instead of session ID
          sessionId,
          title: metadata.title,
          timestamp: new Date()
        };
        setChats(prev => [...prev, newChat]);
      }
        
  
      
    } catch (error) {
    if (tempAgentMessage) { // Add safety check
      setMessages(prev => prev.map(msg => {
        if (msg.id === tempAgentMessage.id) {
          return {
            ...msg,
            status: 'error',
            parts: [{ type: 'text', text: 'Failed to get response' }]
          };
        }
        return msg;
      }));
    }
  } finally {
    // This will ALWAYS run (success or error)
    setInput('');  // <-- Moved here
  }
};
  
const mockFetchChatHistory = async (taskId) => {
  // Replace this with actual fetch when backend is ready
  return {
    jsonrpc: '2.0',
    id: 1,
    result: {
      id: taskId,
      sessionId: 'mock-session-id',
      history: [
        {
          role: 'user',
          parts: [{ type: 'text', text: 'Mock history message' }]
        }
      ],
      metadata: { title: 'Mock History' }
    }
  };
};

// Add chat selection handler
const handleChatSelect = async (chat) => {
  try {
    // Clear current chat
    setMessages([]);
    setIsInitialState(false);
    
    // Set loading state
    const loadingMessage = {
      id: `loading-${Date.now()}`,
      role: 'system',
      parts: [{ type: 'text', text: 'Loading conversation...' }],
      status: 'pending',
      timestamp: new Date()
    };
    setMessages([loadingMessage]);

    // Fetch chat history
    const response = await mockFetchChatHistory(chat.id);
    const { messages: historyMessages, sessionId, taskId } = parseGetResponse(response);
    
    // Update state
    setCurrentSessionId(sessionId);
    setCurrentTaskId(taskId);
    setMessages(historyMessages);
    setActiveChat(chat.id);

  } catch (error) {
    setMessages([{
      id: Date.now(),
      role: 'system',
      parts: [{ type: 'text', text: 'Failed to load conversation' }],
      status: 'error',
      timestamp: new Date()
    }]);
  }
};

  return (
    <div className="app">
      {/* Left Sidebar */}
      <div className="sidebar">
        <div className="logo-container">
          <img src="logo.png" alt="Logo" className="logo" />
        </div>
        
        <button className="new-chat-btn" onClick={handleNewChat}>
          + New Task
        </button>
        
        <div className="chat-history">
        <ChatSection 
          title="Today" 
          chats={chats} 
          daysAgo={0}
          activeChat={activeChat}
          onChatSelect={handleChatSelect}
        />
        <ChatSection 
          title="Yesterday" 
          chats={chats} 
          daysAgo={1}
          activeChat={activeChat}
          onChatSelect={handleChatSelect}
        />
        <ChatSection 
          title="Previous 7 Days" 
          chats={chats} 
          daysAgo={7}
          activeChat={activeChat}
          onChatSelect={handleChatSelect}
        />
        <ChatSection 
          title="Older" 
          chats={chats} 
          daysAgo={8}
          activeChat={activeChat}
          onChatSelect={handleChatSelect}
        />
        </div>
      </div>

      {/* Main Chat Window */}
      <div className="main-chat">
        <div className="chat-header">
          <ModeSelector mode={mode} setMode={setMode} />
        </div>

        {isInitialState ? (
          <div className="initial-prompt">
            <h1>What can I help you with?</h1>
            <div className="input-container centered">
              <form onSubmit={handleSubmit}>
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSubmit(e);
                  }
                }}
                placeholder="Type your message here..."
              />
                <button type="submit">Send</button>
              </form>
            </div>
          </div>
        ) : (
          <>
            <div className="chat-messages">
            {messages.map((message) => (
              <Message key={message.id} message={message} />  // Changed from timestamp to id
            ))}
            </div>
            <div className="input-container">
              <form onSubmit={handleSubmit}>
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSubmit(e);
                  }
                }}
                placeholder="Type your message here..."
              />
                <button type="submit">Send</button>
              </form>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

const Message = ({ message }) => (
  <div className={`message ${message.role}`}>
    {message.status === 'pending' ? (
      <div className="loading-dots">
        <div className="dot"></div>
        <div className="dot"></div>
        <div className="dot"></div>
      </div>
    ) : (
      message.parts.map((part, index) => (
        part.type === 'text' ? (
          <ReactMarkdown key={index}>{part.text}</ReactMarkdown>
        ) : (
          <div key={index}>Unsupported content type</div>
        )
      ))
    )}
  </div>
);

const ModeSelector = ({ mode, setMode }) => {
  return (
    <div className="mode-selector">
      <button
        className={mode === 'send' ? 'active' : ''}
        onClick={() => setMode('send')}
      >
        Send
      </button>
      <button
        className={mode === 'subscribe' ? 'active' : ''}
        onClick={() => setMode('subscribe')}
      >
        Subscribe
      </button>
    </div>
  );
};

const ChatSection = ({ 
  title, 
  chats, 
  daysAgo, 
  activeChat,  // Add prop
  onChatSelect  // Add prop
}) => {
  const now = new Date();
  const filteredChats = chats.filter(chat => {
    const diffTime = Math.abs(now - chat.timestamp);
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    return diffDays >= daysAgo && (daysAgo === 8 ? diffDays > 7 : diffDays < daysAgo);
  });

  if (filteredChats.length === 0) return null;

  return (
    <div className="chat-section">
      <h3>{title}</h3>
      <ul>
        {filteredChats.map(chat => (
          <li 
            key={chat.id} 
            className={`chat-item ${activeChat === chat.id ? 'active' : ''}`}
            onClick={() => onChatSelect(chat)}  // Use passed prop
          >
            {chat.title}
          </li>
        ))}
      </ul>
    </div>
  );
};

export default App;