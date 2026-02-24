import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate('/login');
  }

  return (
    <nav className="w-full py-5 px-6 md:px-12 flex justify-between items-center z-40">
      <div
        className="flex items-center gap-3 cursor-pointer"
        onClick={() => window.location.reload()}
      >
        <div className="w-10 h-10 bg-brand-black rounded-xl flex items-center justify-center text-white shadow-lg shadow-brand-orange/20">
          <i className="fa-solid fa-layer-group text-lg"></i>
        </div>
        <span className="font-display font-bold text-2xl tracking-tight">MAVEN</span>
      </div>

      {user && (
        <div className="flex items-center gap-4">
          <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-white rounded-full border border-gray-100 shadow-sm">
            <div className="w-7 h-7 bg-brand-orange rounded-full flex items-center justify-center text-white text-xs font-bold">
              {user.name?.charAt(0)?.toUpperCase() || 'U'}
            </div>
            <span className="text-sm font-medium text-brand-black">{user.name}</span>
          </div>
          <button
            onClick={handleLogout}
            className="text-gray-400 hover:text-brand-orange transition-colors text-sm font-medium flex items-center gap-1.5"
          >
            <i className="fa-solid fa-arrow-right-from-bracket"></i>
            <span className="hidden sm:inline">Logout</span>
          </button>
        </div>
      )}
    </nav>
  );
}
