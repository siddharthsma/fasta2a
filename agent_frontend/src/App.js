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
  const [attachedFiles, setAttachedFiles] = useState([]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  
  // Add useEffect for fetching the tasks and updating the chats - on initial load.
  useEffect(() => {
    const fetchTasks = async () => {
      
      try {
        const response = await fetch(`${API_CONFIG.SERVER_URL}/tasks?fields=id,status,metadata`, {
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
          servers: [API_CONFIG.NATS_WS_URL]
        });
        
        subscription.current = natsConnection.current.subscribe('state.updates');
        
        // Message listener
        (async () => {
          for await (const msg of subscription.current) {
            const rawData = new TextDecoder().decode(msg.data);
            const update = JSON.parse(rawData);
            console.log("--- NATS update ---")
            console.log(update)
            console.log("--- NATS update end ---")
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
      console.log("handleNATSUpdate: ", update);
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
    if (!input.trim() && attachedFiles.length === 0) return;

    try {
      const tempMessageId = uuidv4();

      // Convert files to base64
      const filesWithBase64 = await Promise.all(
        attachedFiles.map(async (file) => {
          const base64 = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result.split(',')[1]);
            reader.onerror = error => reject(error);
            reader.readAsDataURL(file);
          });
          return {
            name: file.name,
            type: file.type,
            base64 
          };
        })
      );

      const userMessage = {
        id: tempMessageId,
        role: 'user',
        parts: [
          ...(input.trim() ? [{ type: 'text', text: input }] : []),
          ...attachedFiles.map(file => ({
            type: 'file',
            file: {
              name: file.name,
              mimeType: file.type
            }
          }))
        ],
        status: 'pending',
        timestamp: new Date()
      };
  

      let requestBody;

      // For new tasks
      if (!currentTaskId) {
        const newTaskId = uuidv4();
        const newSessionId = uuidv4();
        const taskName = truncateTitle(input || attachedFiles[0]?.name || 'File Upload');
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
          input,
          filesWithBase64,
          newSessionId,
          newTaskId,
          metadata
        );
      } else {
        // Existing task - append message
        setMessages(prev => [...prev, userMessage]);

        // Build request for existing task
        requestBody = buildSendRequest(
          input,
          filesWithBase64,
          currentSessionId,
          currentTaskId,
          {}
        );
      }

      const response = await fetch(`${API_CONFIG.SERVER_URL}/rpc`, {
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
      setAttachedFiles([]);

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
    const response = await fetch(`${API_CONFIG.SERVER_URL}/rpc`, {
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

// Add file handler
const handleFileUpload = (e) => {
  const files = Array.from(e.target.files);
  setAttachedFiles(prev => [...prev, ...files]);
};

// Add file removal handler
const removeFile = (fileName) => {
  setAttachedFiles(prev => prev.filter(f => f.name !== fileName));
};



  return (
    <div className="app">
      {/* Left Sidebar */}
      <div className={`sidebar ${isSidebarOpen ? 'open' : 'collapsed'}`}>
        <div className="logo-container">
          <button onClick={() => setIsSidebarOpen(!isSidebarOpen)} className="sidebar-toggle">
            {isSidebarOpen ? (
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M3 12h18M3 6h18M3 18h18"/>
              </svg>
            ) : (
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M4 6h16M4 12h16M4 18h16"/>
              </svg>
            )}
          </button>
          {isSidebarOpen && <h2>SmartA2A</h2>}
        </div>

        <button className="new-chat-btn" onClick={handleNewChat}>
          {isSidebarOpen ? '+ New Task' : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path d="M12 5v14M5 12h14"/>
            </svg>
          )}
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
          isSidebarOpen={isSidebarOpen}
        />
        <ChatSection 
          title="Yesterday" 
          chats={chats} 
          daysAgo={1}
          activeChat={activeChat}
          onChatSelect={handleChatSelect}
          hasUpdates={hasUpdates}
          setHasUpdates={setHasUpdates}
          isSidebarOpen={isSidebarOpen}
        />
        <ChatSection 
          title="Previous 7 Days" 
          chats={chats} 
          daysAgo={7}
          activeChat={activeChat}
          onChatSelect={handleChatSelect}
          hasUpdates={hasUpdates}
          setHasUpdates={setHasUpdates}
          isSidebarOpen={isSidebarOpen}
        />
        <ChatSection 
          title="Older" 
          chats={chats} 
          daysAgo={8}
          activeChat={activeChat}
          onChatSelect={handleChatSelect}
          hasUpdates={hasUpdates}
          setHasUpdates={setHasUpdates}
          isSidebarOpen={isSidebarOpen}
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
                <div className="message-input-wrapper">
                  {attachedFiles.length > 0 && (
                    <div className="attached-files">
                      {attachedFiles.map((file) => (
                        <div key={file.name} className="file-pill">
                          <span>{file.name}</span>
                          <button
                            type="button"
                            onClick={() => removeFile(file.name)}
                            className="remove-file"
                          >
                            ×
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="input-area">
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
                      rows="1"
                      onInput={(e) => {
                        e.target.style.height = 'auto';
                        e.target.style.height = e.target.scrollHeight + 'px';
                      }}
                    />
                    <div className="button-container">
                      <label className="file-upload-button">
                        <input
                          type="file"
                          multiple
                          onChange={handleFileUpload}
                          style={{ display: 'none' }}
                        />
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="file-upload-icon">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13" />
                        </svg>
                      </label>
                      <button type="submit" className="send-button">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" className="h-4 w-4">
                          <path d="M.5 1.163A1 1 0 0 1 1.97.28l12.868 6.837a1 1 0 0 1 0 1.766L1.969 15.72A1 1 0 0 1 .5 14.836V10.33a1 1 0 0 1 .816-.983L8.5 8 1.316 6.653A1 1 0 0 1 .5 5.67V1.163Z" fill="currentColor"></path>
                        </svg>
                      </button>
                    </div>
                  </div>
                </div>
              </form>
            </div>
          </div>
        ) : (
          <>
            <div className="chat-messages">
              {messages.map((message) => (
                <Message key={message.id} message={message} />
              ))}
              <div ref={messagesEndRef} />
            </div>
            <div className="input-container">
              <form onSubmit={handleSubmit}>
                <div className="message-input-wrapper">
                  {attachedFiles.length > 0 && (
                    <div className="attached-files">
                      {attachedFiles.map((file) => (
                        <div key={file.name} className="file-pill">
                          <span>{file.name}</span>
                          <button
                            type="button"
                            onClick={() => removeFile(file.name)}
                            className="remove-file"
                          >
                            ×
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="input-area">
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
                      rows="1"
                      onInput={(e) => {
                        e.target.style.height = 'auto';
                        e.target.style.height = e.target.scrollHeight + 'px';
                      }}
                    />
                    <div className="button-container">
                      <label className="file-upload-button">
                        <input
                          type="file"
                          multiple
                          onChange={handleFileUpload}
                          style={{ display: 'none' }}
                        />
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="file-upload-icon">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13" />
                        </svg>
                      </label>
                      <button type="submit" className="send-button">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" className="h-4 w-4">
                          <path d="M.5 1.163A1 1 0 0 1 1.97.28l12.868 6.837a1 1 0 0 1 0 1.766L1.969 15.72A1 1 0 0 1 .5 14.836V10.33a1 1 0 0 1 .816-.983L8.5 8 1.316 6.653A1 1 0 0 1 .5 5.67V1.163Z" fill="currentColor"></path>
                        </svg>
                      </button>
                    </div>
                  </div>
                </div>
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
      {message.parts.map((part, index) => {
        if (part.type === 'text') {
          return (
            <div className="markdown-content" key={index}>
              <ReactMarkdown 
                remarkPlugins={[remarkGfm]}
                components={{
                  // Enhanced markdown components
                  h1: ({ node, ...props }) => <h1 className="md-h1" {...props} />,
                  h2: ({ node, ...props }) => <h2 className="md-h2" {...props} />,
                  h3: ({ node, ...props }) => <h3 className="md-h3" {...props} />,
                  p: ({ node, ...props }) => <p className="md-p" {...props} />,
                  ul: ({ node, ...props }) => <ul className="md-ul" {...props} />,
                  ol: ({ node, ...props }) => <ol className="md-ol" {...props} />,
                  li: ({ node, ...props }) => <li className="md-li" {...props} />,
                  code({ node, inline, className, children, ...props }) {
                    return !inline ? (
                      <div className="code-block-wrapper">
                        <pre className="code-block">
                          <code className={className} {...props}>
                            {children}
                          </code>
                        </pre>
                      </div>
                    ) : (
                      <code className="inline-code" {...props}>
                        {children}
                      </code>
                    );
                  },
                  blockquote: ({ node, children, ...props }) => (
                    <blockquote className="md-blockquote" {...props}>
                      {children}
                    </blockquote>
                  ),
                  table: ({ node, children, ...props }) => (
                    <div className="table-wrapper">
                      <table className="md-table" {...props}>
                        {children}
                      </table>
                    </div>
                  ),
                  a: ({ node, children, ...props }) => (
                    <a className="md-link" {...props} target="_blank" rel="noopener noreferrer">
                      {children}
                    </a>
                  ),
                  img: ({ node, ...props }) => (
                    <img className="md-image" {...props} alt="content" />
                  ),
                  hr: ({ node, ...props }) => <hr className="md-hr" {...props} />,
                }}
              >
                {part.text}
              </ReactMarkdown>
            </div>
          );
        }
        if (part.type === 'file') {
          return (
            <div key={index} className="file-message">
              <div className="file-icon">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                </svg>
              </div>
              <div className="file-details">
                <span className="file-name">{part.file.name}</span>
                <span className="file-type">{part.file.mimeType}</span>
              </div>
            </div>
          );
        }
        return <div key={index}>Unsupported content type</div>;
      })}
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
        className={`mode-btn ${mode === 'send' ? 'active' : ''}`}
        onClick={() => setMode('send')}
      >
        Send
      </button>
      <button
        className={`mode-btn ${mode === 'subscribe' ? 'active' : ''}`}
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
  activeChat,
  onChatSelect,
  hasUpdates,
  setHasUpdates,
  isSidebarOpen
}) => {
  const [hoveredChatId, setHoveredChatId] = useState(null);
  const [tooltipPosition, setTooltipPosition] = useState({ x: 0, y: 0 });
  const now = new Date();
  const filteredChats = chats.filter(chat => {
    const taskDate = new Date(chat.timestamp);
    const diffDays = Math.floor((now - taskDate) / (1000 * 60 * 60 * 24));
    
    if (daysAgo === 0) return diffDays === 0;
    if (daysAgo === 1) return diffDays === 1;
    if (daysAgo === 7) return diffDays > 1 && diffDays <= 7;
    return diffDays > 7;
  });

  if (!isSidebarOpen && filteredChats.length === 0) return null;

  const handleMouseEnter = (e, chat) => {
    if (!isSidebarOpen) {
      const rect = e.currentTarget.getBoundingClientRect();
      setTooltipPosition({
        x: rect.left + rect.width + 10,
        y: rect.top + window.scrollY
      });
      setHoveredChatId(chat.id);
    }
  };

  return (
    <div className="chat-section">
      {isSidebarOpen && <h3>{title}</h3>}
      <ul>
        {filteredChats.map(chat => (
          <li 
            key={chat.id} 
            className={`chat-item ${activeChat === chat.id ? 'active' : ''}`}
            onMouseEnter={(e) => handleMouseEnter(e, chat)}
            onMouseLeave={() => setHoveredChatId(null)}
            onClick={() => {
              onChatSelect(chat);
              setHasUpdates(prev => {
                const newSet = new Set(prev);
                newSet.delete(chat.id);
                return newSet;
              });
            }}
          >
            {isSidebarOpen ? (
              <>
                <span className="chat-title">{chat.title}</span>
                {hasUpdates.has(chat.id) && <span className="update-dot"></span>}
              </>
            ) : (
              <div className="collapsed-chat-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
                {hasUpdates.has(chat.id) && <span className="update-dot"></span>}
              </div>
            )}
            {!isSidebarOpen && hoveredChatId === chat.id && (
              <Tooltip text={chat.title} position={tooltipPosition} />
            )}
          </li>
        ))}
      </ul>
    </div>
  );
};

const Tooltip = ({ text, position }) => {
  return (
    <div 
      className="chat-tooltip"
      style={{
        left: position.x,
        top: position.y
      }}
    >
      {text}
    </div>
  );
};

export default App;