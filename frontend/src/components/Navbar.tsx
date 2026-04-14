import { Link, useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { HiMenu, HiX } from 'react-icons/hi';
import logo from '../assets/NCULogo.png';

const navItems = [
  { path: '/', label: '首頁' },
  { path: '/assessment', label: '興趣量表' },
  { path: '/courses', label: '課程資訊' },
  { path: '/course-search', label: '課程搜尋' },
  { path: '/projects', label: '研究計畫' },
  { path: '/resources', label: '資源連結' },
];

export default function Navbar() {
  const location = useLocation();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [location.pathname]);

  return (
    <nav className="sticky top-0 z-50 border-b border-white/70 bg-white/80 backdrop-blur-xl">
      <div className="page-container">
        <div className="flex h-16 items-center justify-between">
          <Link to="/" className="flex items-center space-x-3 transition duration-200 hover:-translate-y-0.5">
            <img src={logo} alt="國立中央大學" className="h-10 w-10 object-contain" />
            <div className="hidden sm:block">
              <div className="text-sm font-bold text-primary-900">國立中央大學</div>
              <div className="text-xs text-slate-500">科系探索平台</div>
            </div>
          </Link>

          <div className="hidden items-center space-x-1 md:flex">
            {navItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                className={`nav-chip ${location.pathname === item.path ? 'nav-chip-active' : ''}`}
              >
                {item.label}
              </Link>
            ))}
          </div>

          <button
            type="button"
            onClick={() => setIsMobileMenuOpen((prev) => !prev)}
            className="rounded-xl p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 md:hidden"
            aria-label={isMobileMenuOpen ? '關閉導覽選單' : '開啟導覽選單'}
            aria-expanded={isMobileMenuOpen}
          >
            {isMobileMenuOpen ? <HiX className="h-6 w-6" /> : <HiMenu className="h-6 w-6" />}
          </button>
        </div>

        {isMobileMenuOpen ? (
          <div className="border-t border-slate-200 py-3 md:hidden">
            <div className="flex flex-col gap-2">
              {navItems.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`rounded-2xl px-4 py-3 text-sm font-medium transition ${
                    location.pathname === item.path
                      ? 'bg-primary-900 text-white'
                      : 'bg-white text-slate-700 hover:bg-slate-100'
                  }`}
                >
                  {item.label}
                </Link>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </nav>
  );
}
