import { Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import UsersPage from './pages/UsersPage';
import HumanReviewPage from './pages/HumanReviewPage';

function App() {
  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <header className="bg-slate-800 text-white shadow">
        <div className="max-w-full mx-auto px-3 sm:px-4 py-3 flex items-center justify-between gap-2 min-w-0">
          <h1 className="text-base sm:text-lg font-semibold truncate">Knowledge Ingestion Admin Console</h1>
          <nav className="flex gap-2 sm:gap-4 shrink-0">
            <NavLink
              to="/"
              className={({ isActive }) =>
                `px-3 py-1 rounded ${isActive ? 'bg-slate-600' : 'hover:bg-slate-700'}`
              }
            >
              Dashboard
            </NavLink>
            <NavLink
              to="/users"
              className={({ isActive }) =>
                `px-3 py-1 rounded ${isActive ? 'bg-slate-600' : 'hover:bg-slate-700'}`
              }
            >
              Users
            </NavLink>
            <NavLink
              to="/review"
              className={({ isActive }) =>
                `px-3 py-1 rounded ${isActive ? 'bg-slate-600' : 'hover:bg-slate-700'}`
              }
            >
              Review
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="flex-1 max-w-full mx-auto w-full p-3 sm:p-4 min-w-0">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/users" element={<UsersPage />} />
          <Route path="/review" element={<HumanReviewPage />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
