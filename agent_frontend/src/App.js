import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { v4 as uuidv4 } from 'uuid';
import API_CONFIG from './config';
import { buildSendRequest, parseSendResponse, truncateTitle, parseGetResponse, buildGetRequest } from './utils/api';
import './App.css';
import { connect } from 'nats.ws'; // Browser-compatible NATS client

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [chats, setChats] = useState([]);
  const [activeChat, setActiveChat] = useState(null);
  const [isInitialState, setIsInitialState] = useState(true);
  const [mode, setMode] = useState('send');
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [currentTaskId, setCurrentTaskId] = useState(null);
  const messagesEndRef = useRef(null);
  const natsConnection = useRef(null);
  const subscription = useRef(null);

  // Add scroll effect
  useEffect(() => {
    scrollToBottom();
  }, [messages]); // Trigger when messages change

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    const fetchTasks = async () => {
      try {
        const response = await fetch(`${API_CONFIG.BASE_URL}/tasks?fields=id,status,metadata`, {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) throw new Error('Failed to fetch tasks');
        const tasks = await response.json();
        
        const transformedChats = tasks.map(task => ({
          id: task.id,
          sessionId: task.sessionId,
          title: task.metadata?.task_name || 'Untitled Task',
          timestamp: new Date(task.status.timestamp)
        }));
  
        setChats(transformedChats);
      } catch (error) {
        console.error('Error loading tasks:', error);
      }
    };
  
    fetchTasks();
  }, []);


  // Add useEffect for connection management
  useEffect(() => {
    const setupNATS = async () => {
      try {
        natsConnection.current = await connect({
          servers: [`${API_CONFIG.NATS_URL}`]
        });
        
        subscription.current = natsConnection.current.subscribe('state.updates');
        
        // Message listener
        (async () => {
          for await (const msg of subscription.current) {
            const rawData = new TextDecoder().decode(msg.data);
            const update = JSON.parse(rawData);
            handleNATSUpdate(update);
          }
        })();
      } catch (error) {
        console.error('NATS connection failed:', error);
      }
    };

    setupNATS();

    // Cleanup on unmount
    return () => {
      if (subscription.current) subscription.current.unsubscribe();
      if (natsConnection.current) natsConnection.current.close();
    };
  }, []);

  // Handle NATS updates
  const handleNATSUpdate = (update) => {
    setMessages((prev) => {
      return prev.map((msg) => {
        // Match both temporary and finalized IDs
        const isTargetMessage = msg.id === `temp-${update.taskId}` || msg.id === update.taskId;
        
        if (!isTargetMessage) return msg;
        if (msg.status === 'complete') return msg; // Ignore updates for completed messages

        // Merge message parts correctly
        const mergedParts = update.parts?.length > 0
          ? update.parts // Replace with new parts (assuming full message updates)
          : msg.parts;

        // Generate final ID only once on first completion
        const newId = update.complete && msg.id.startsWith('temp-')
          ? uuidv4()
          : msg.id;

        return {
          ...msg,
          id: newId,
          parts: mergedParts,
          status: update.complete ? 'complete' : 'streaming',
          timestamp: new Date()
        };
      });
    });
  };

  const handleNewChat = () => {
    setCurrentSessionId(null);
    setMessages([]);
    setIsInitialState(true);
    setActiveChat(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;
  
    try {
      // Generate fresh IDs for every new task
      const newTaskId = uuidv4();
      const sessionId = currentSessionId || uuidv4();
      const isNewSession = !currentSessionId;
  
      // Clear input IMMEDIATELY
      setInput('');
  
      // Create user message
      const userMessage = {
        id: Date.now(),
        role: 'user',
        parts: [{ type: 'text', text: input }],
        status: 'complete',
        timestamp: new Date()
      };
  
      // Create temporary agent message with NEW task ID
      const tempAgentMessage = {
        id: `temp-${newTaskId}`,
        role: 'agent',
        parts: [{ type: 'text', text: '' }],
        status: 'pending',
        timestamp: new Date()
      };
  
      // Update state with both messages
      setMessages(prev => [...prev, userMessage, tempAgentMessage]);
      setIsInitialState(false);
  
      // Update session/task tracking
      setCurrentTaskId(newTaskId);
      if (isNewSession) setCurrentSessionId(sessionId);
  
      // Build request with fresh IDs
      const requestBody = buildSendRequest(
        input,
        sessionId,
        newTaskId,
        { task_name: truncateTitle(input) }
      );
  
      // Send request
      const response = await fetch(`${API_CONFIG.BASE_URL}/rpc`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
      });
  
      if (!response.ok) throw new Error('Request failed');
  
      // Add to chat history if new session
      if (isNewSession) {
        const newChat = {
          id: newTaskId,
          sessionId,
          title: truncateTitle(input),
          timestamp: new Date()
        };
        setChats(prev => [...prev, newChat]);
        setActiveChat(newTaskId);
      }
  
    } catch (error) {
      // Update error state for the temporary message
      setMessages(prev => prev.map(msg => {
        if (msg.id.startsWith('temp-')) {
          return {
            ...msg,
            status: 'error',
            parts: [{ type: 'text', text: 'Failed to get response' }]
          };
        }
        return msg;
      }));
    }
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
    const requestBody = buildGetRequest(chat.id);
    const response = await fetch(`${API_CONFIG.BASE_URL}/rpc`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody)
    });

    if (!response.ok) throw new Error('Network response was not ok');
    const responseData = await response.json();

    const { messages: historyMessages, sessionId, taskId } = parseGetResponse(responseData);
    
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
              <div ref={messagesEndRef} />
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
          <div className="markdown-content" key={index}>
            <ReactMarkdown 
              remarkPlugins={[remarkGfm]}
              components={{
                code({ node, inline, className, children, ...props }) {
                  return !inline ? (
                    <div className="code-block">
                      <code className={className} {...props}>
                        {children}
                      </code>
                    </div>
                  ) : (
                    <code className="inline-code" {...props}>
                      {children}
                    </code>
                  );
                },
                pre({ node, children, ...props }) {
                  return <pre className="pre-block" {...props}>{children}</pre>;
                },
                blockquote({ node, children, ...props }) {
                  return <blockquote className="quote-block" {...props}>{children}</blockquote>;
                },
                ol({ node, children, ...props }) {
                  return <ol className="numbered-list" {...props}>{children}</ol>;
                },
                ul({ node, children, ...props }) {
                  return <ul className="bulleted-list" {...props}>{children}</ul>;
                }
              }}
            >
              {part.text}
            </ReactMarkdown>
          </div>
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
    const now = new Date();
    const taskDate = new Date(chat.timestamp);
    const diffDays = Math.floor((now - taskDate) / (1000 * 60 * 60 * 24));
    
    if (daysAgo === 0) return diffDays === 0; // Today
    if (daysAgo === 1) return diffDays === 1; // Yesterday
    if (daysAgo === 7) return diffDays > 1 && diffDays <= 7; // Last 7 days
    return diffDays > 7; // Older
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