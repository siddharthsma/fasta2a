import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { v4 as uuidv4 } from 'uuid';
import { API_CONFIG } from './config';
import { buildSendRequest, parseSendResponse, truncateTitle } from './utils/api';
import './App.css';

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [chats, setChats] = useState([]);
  const [activeChat, setActiveChat] = useState(null);
  const [isInitialState, setIsInitialState] = useState(true);
  const [mode, setMode] = useState('send');
  const [currentSessionId, setCurrentSessionId] = useState(null);

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
      let sessionId = currentSessionId;
      let metadata = {};

      // Create new chat session if needed
      if (!sessionId) {
        sessionId = uuidv4();
        metadata.title = truncateTitle(input);
        setCurrentSessionId(sessionId);
        setChats(prev => [...prev, {
          id: sessionId,
          title: metadata.title,
          timestamp: new Date(),
          sessionId
        }]);
      }

      // Build and send request
      const requestBody = buildSendRequest(input, sessionId, metadata);
      const response = await fetch(API_CONFIG.BASE_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
      });

      if (!response.ok) throw new Error('Network response was not ok');

      const responseData = await response.json();
      const { messages: parsedMessages } = parseSendResponse(responseData);

      // Update UI state
      setMessages(parsedMessages);
      setIsInitialState(false);
      setInput('');
    } catch (error) {
      console.error('Error submitting message:', error);
      // Add error handling UI here
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
          + New Chat
        </button>
        
        <div className="chat-history">
          <ChatSection title="Today" chats={chats} daysAgo={0} />
          <ChatSection title="Yesterday" chats={chats} daysAgo={1} />
          <ChatSection title="Previous 7 Days" chats={chats} daysAgo={7} />
          <ChatSection title="Older" chats={chats} daysAgo={8} />
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
                  <Message key={message.timestamp} message={message} />
              ))}
            </div>
            <div className="input-container">
              <form onSubmit={handleSubmit}>
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
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
    {message.parts.map((part, index) => (
      part.type === 'text' ? (
        <ReactMarkdown key={index}>{part.text}</ReactMarkdown>
      ) : (
        <div key={index}>Unsupported content type</div>
      )
    ))}
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

const ChatSection = ({ title, chats, daysAgo }) => {
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
          <li key={chat.id} className="chat-item">
            {chat.title}
          </li>
        ))}
      </ul>
    </div>
  );
};

export default App;