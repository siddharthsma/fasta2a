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
  const [hasUpdates, setHasUpdates] = useState(new Set());

  
  // Add useEffect for fetching the tasks and updating the chats - on initial load.
  useEffect(() => {
    const fetchTasks = async () => {
      try {
        const response = await fetch('http://localhost/tasks?fields=id,status,metadata', {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) throw new Error('Failed to fetch tasks');
        const tasks = await response.json();
        
        const transformedChats = tasks.map(task => ({
          id: task.id,
          sessionId: task.sessionId,
          title: task.metadata?.taskName || 'Untitled Task',
          timestamp: new Date(task.status.timestamp)
        }));
  
        setChats(transformedChats);
      } catch (error) {
        console.error('Error loading tasks:', error);
      }
    };
  
    fetchTasks();
  }, []);


  // Add useEffect for connecting to the NATS server and subscribing to updates.
  useEffect(() => {
    const setupNATS = async () => {
      try {
        natsConnection.current = await connect({
          servers: ['ws://localhost/ws']
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

  // Add scroll effect
  useEffect(() => {
    scrollToBottom();
  }, [messages]); // Trigger when messages change

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  // Handle NATS updates
  const handleNATSUpdate = (update) => {
    /*
    TODO: when a new update arrives, there are 3 cases:
    1. the update is associated with a taskId that is already in the chats and the current active chat is the same as the taskId.
    2. the update is associated with a taskId that is not in the chats.
    3. the update is associated with a taskId that is in the chats, but the taskId is not the current active chat.

    In case 1, we should update the messages.
    In case 2, we should create a new chat and update the chats. This should update the sidebar (creating a new entry in the sidebar).
    In case 3, we should update the sidebar with a red dot next to the chat showing that there is a new message/s. 
    */
    setChats(prevChats => {
      const existingChat = prevChats.find(c => c.id === update.taskId);
      const isActive = activeChat === update.taskId;
      
      // Case 1: Update active chat
      if (existingChat && isActive) {
        setMessages(prev => [...prev, ...update.messages]);
      }
      // Case 2: New chat creation
      else if (!existingChat) {
        const newChat = {
          id: update.taskId,
          sessionId: update.sessionId,
          title: update.taskName || 'New Task',
          timestamp: new Date(),
          hasUpdates: false
        };
        return [...prevChats, newChat];
      }
      // Case 3: Update existing non-active chat
      else if (existingChat && !isActive) {
        setHasUpdates(prev => new Set([...prev, update.taskId]));
      }
      
      return prevChats;
    });
  };

  const handleNewChat = () => {
    setCurrentSessionId(null);
    setCurrentTaskId(null);
    setMessages([]);
    setIsInitialState(true);
    setActiveChat(null);
  };

  const handleSubmit = async (e) => {
    /* 
    TODO: The main job of this callback is to send a post request to http://localhost/rpc .
    If this is a new task and therefore, currentTaskId is null, it should create a new taskId and sessionId (uuid gen) and also create a new sidebar entry for the new task by updating chats.
    It should also set the chat as the active chat and update the isInitialState to false. Offcourse the post request should be sent with the new taskId and sessionId.
    If the currentTaskId is set then nothing needs to be done apart from sending the post request to http://localhost/rpc.
    */
    e.preventDefault();
    if (!input.trim()) return;

    try {
      const tempMessageId = uuidv4();
      const userMessage = {
        id: tempMessageId,
        role: 'user',
        parts: [{ type: 'text', text: input }],
        status: 'pending',
        timestamp: new Date()
      };

      let requestBody;

      // For new tasks
      if (!currentTaskId) {
        const newTaskId = uuidv4();
        const newSessionId = uuidv4();
        const taskName = truncateTitle(input);
        const metadata = { taskName: taskName };

        // Add temporary message
        setMessages([userMessage]);
        
        // Create new chat entry
        const newChat = {
          id: newTaskId,
          sessionId: newSessionId,
          title: taskName,
          timestamp: new Date(),
          hasUpdates: false
        };
        setChats(prev => [newChat, ...prev]);
        setActiveChat(newTaskId);
        setCurrentTaskId(newTaskId);
        setCurrentSessionId(newSessionId);
        setIsInitialState(false);

        // Build request with proper parameters
        requestBody = buildSendRequest(
          input,         // message content
          newSessionId,   // sessionId
          newTaskId,      // taskId
          metadata        // metadata
        );
      } else {
        // Existing task - append message
        setMessages(prev => [...prev, userMessage]);

        // Build request for existing task
        requestBody = buildSendRequest(
          input,
          currentSessionId,
          currentTaskId,
          {} // empty metadata for existing tasks
        );
      }

      const response = await fetch('http://localhost/rpc', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
      });



      if (!response.ok) throw new Error('Request failed');
      
      const responseData = await response.json();
      const { messages: serverMessages } = parseSendResponse(responseData);

      // Replace temporary message with actual response
      setMessages(prev => [
        ...prev.map(msg => 
          msg.id === tempMessageId 
            ? { ...msg, status: 'complete' } // Update user message status
            : msg
        ),
        // Add agent response as new message
        ...serverMessages.map(msg => ({
          ...msg,
          id: uuidv4(),
          timestamp: new Date(),
          status: 'complete'
        }))
      ]);

      setInput('');
    } catch (error) {
      console.error('Submit error:', error);
      setMessages(prev => prev.map(msg => 
        msg.status === 'pending' 
          ? { ...msg, status: 'error', parts: [{ type: 'text', text: 'Message failed to send' }] }
          : msg
      ));
    }
  };
  

// Add chat selection handler
const handleChatSelect = async (chat) => {
  try {
    // Clear current chat
    setMessages([]);
    setIsInitialState(false);

    // Fetch chat history
    const requestBody = buildGetRequest(chat.id);
    const response = await fetch('http://localhost/rpc', {
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
          hasUpdates={hasUpdates}
          setHasUpdates={setHasUpdates}
        />
        <ChatSection 
          title="Yesterday" 
          chats={chats} 
          daysAgo={1}
          activeChat={activeChat}
          onChatSelect={handleChatSelect}
          hasUpdates={hasUpdates}
          setHasUpdates={setHasUpdates}
        />
        <ChatSection 
          title="Previous 7 Days" 
          chats={chats} 
          daysAgo={7}
          activeChat={activeChat}
          onChatSelect={handleChatSelect}
          hasUpdates={hasUpdates}
          setHasUpdates={setHasUpdates}
        />
        <ChatSection 
          title="Older" 
          chats={chats} 
          daysAgo={8}
          activeChat={activeChat}
          onChatSelect={handleChatSelect}
          hasUpdates={hasUpdates}
          setHasUpdates={setHasUpdates}
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
  <div className={`message ${message.role} ${message.status}`}>
    {/* Message Content - Always Visible */}
    <div className="message-content">
      {message.parts.map((part, index) => (
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
      ))}
    </div>

    {/* Loading Dots - Only for Pending Messages */}
    {message.status === 'pending' && (
      <div className="loading-dots">
        <div className="dot"></div>
        <div className="dot"></div>
        <div className="dot"></div>
      </div>
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
  onChatSelect,
  hasUpdates,
  setHasUpdates
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
            onClick={() => {
              onChatSelect(chat);

              // Clear update notification when selecting
              setHasUpdates(prev => {
                const newSet = new Set(prev);
                newSet.delete(chat.id);
                return newSet;
              });
            
            }}  // Use passed prop
          >
            {chat.title}
            {hasUpdates.has(chat.id) && ( // NEW: Notification dot
              <span className="update-dot"></span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
};

export default App;