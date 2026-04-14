import { Link, useLocation } from 'react-router-dom';
import { HiMenu } from 'react-icons/hi';
import logo from '../assets/NCULogo.png';

export default function Navbar() {
  const location = useLocation();

  const navItems = [
    { path: '/', label: '首頁' },
    { path: '/assessment', label: '興趣量表' },
    { path: '/courses', label: '課程資訊' },
    { path: '/course-search', label: '課程搜尋' },
    { path: '/projects', label: '研究計畫' },
  ];

  return (
    <nav className="bg-white border-b border-gray-200 sticky top-0 z-50">
      <div className="page-container">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link to="/" className="flex items-center space-x-3">
            <img
              src={logo}
              alt="中央大學校徽"
              className="w-10 h-10 object-contain"
            />
            <div className="hidden sm:block">
              <div className="text-sm font-bold text-primary-900">國立中央大學</div>
              <div className="text-xs text-gray-600">科系探索平台</div>
            </div>
          </Link>

          {/* Navigation Links */}
          <div className="hidden md:flex items-center space-x-1">
            {navItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                className={`px-4 py-2 rounded-md transition-colors font-medium text-sm ${
                  location.pathname === item.path
                    ? 'bg-primary-700 text-white'
                    : 'text-gray-700 hover:bg-gray-100'
                }`}
              >
                {item.label}
              </Link>
            ))}
          </div>

          {/* Mobile Menu Button */}
          <button className="md:hidden text-gray-600 hover:text-gray-900">
            <HiMenu className="w-6 h-6" />
          </button>
        </div>
      </div>
    </nav>
  );
}
