import { Routes, Route } from 'react-router-dom';
import Dashboard from './components/Dashboard/Dashboard';
import ChatView from './views/ChatView';
import TrainingView from './views/TrainingView';
import './App.css';

function App() {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/chat" element={<ChatView />} />
      <Route path="/training" element={<TrainingView />} />
      {/* Placeholder routes for future modules */}
      <Route path="/memory" element={<ComingSoon title="Memory Bank" />} />
      <Route path="/agents" element={<ComingSoon title="Agent Workshop" />} />
      <Route path="/analytics" element={<ComingSoon title="Analytics" />} />
      <Route path="/logs" element={<ComingSoon title="Logs & History" />} />
    </Routes>
  );
}

// Placeholder component for routes not yet implemented
function ComingSoon({ title }: { title: string }) {
  return (
    <div style={{
      minHeight: '100vh',
      background: '#121212',
      color: '#e0e0e0',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '20px'
    }}>
      <h1>{title}</h1>
      <p>Coming soon...</p>
      <a
        href="/"
        style={{
          color: '#4a9eff',
          textDecoration: 'none',
          padding: '10px 20px',
          border: '1px solid #4a9eff',
          borderRadius: '6px'
        }}
      >
        ← Back to Dashboard
      </a>
    </div>
  );
}

export default App;
