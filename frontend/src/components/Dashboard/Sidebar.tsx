import { NavLink } from 'react-router-dom';
import './Sidebar.css';

const Sidebar = () => {
  const menuItems = [
    { path: '/projects', label: 'Projects', icon: '📁' },
    { path: '/agents', label: 'Agents', icon: '🤖' },
    { path: '/journal-blocks', label: 'Journal Blocks', icon: '📝' },
    { path: '/tools', label: 'Tools', icon: '🔧' },
    { path: '/terminal', label: 'Terminal', icon: '💻' },
    { path: '/coding', label: 'Coding', icon: '⚡' },
    { path: '/chat', label: 'Chat', icon: '💬' },
  ];

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <h1 className="sidebar-title">Appletta</h1>
      </div>
      <nav className="sidebar-nav">
        {menuItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `sidebar-item ${isActive ? 'sidebar-item-active' : ''}`
            }
          >
            <span className="sidebar-icon">{item.icon}</span>
            <span className="sidebar-label">{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-footer">
        <NavLink to="/settings" className="sidebar-item">
          <span className="sidebar-icon">⚙️</span>
          <span className="sidebar-label">Settings</span>
        </NavLink>
      </div>
    </div>
  );
};

export default Sidebar;
