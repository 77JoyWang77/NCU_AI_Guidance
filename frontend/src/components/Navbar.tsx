import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link, useLocation } from 'react-router-dom';
import { HiMenu, HiX } from 'react-icons/hi';
import logo from '../assets/NCULogo.png';
import GoogleLoginButton from './GoogleLoginButton';

const navItems = [
  { path: '/', label: '首頁' },
  { path: '/assessment', label: '興趣量表' },
  { path: '/courses', label: '課程資訊' },
  { path: '/course-search', label: '課程搜尋' },
  { path: '/projects', label: '研究計畫' },
  { path: '/resources', label: '資源連結' },
  { path: '/curriculum', label: '修課規定' },
];

function MobileMenuOverlay({
  pathname,
  onClose,
}: {
  pathname: string;
  onClose: () => void;
}) {
  return createPortal(
    <div className="fixed inset-0 z-[9999] bg-transparent md:hidden">
      <div className="w-full overflow-hidden border-b border-slate-200 bg-white shadow-2xl">
        <div className="flex h-16 items-center justify-between px-4">
          <Link to="/" className="flex items-center space-x-3" onClick={onClose}>
            <img src={logo} alt="國立中央大學科系探索平台" className="h-10 w-10 object-contain" />
          </Link>

          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-11 w-11 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
            aria-label="關閉導覽選單"
          >
            <HiX className="h-7 w-7" />
          </button>
        </div>

        <div className="w-full max-h-[calc(100vh-5rem)] overflow-y-auto border-t border-slate-200 bg-white px-4 py-4">
          <div className="flex w-full flex-col items-stretch gap-2">
            {navItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                onClick={onClose}
                className={`block w-full self-stretch px-4 py-4 text-base font-medium transition ${
                  pathname === item.path
                    ? 'bg-primary-900 text-white'
                    : 'bg-white text-slate-800 hover:bg-slate-50'
                }`}
              >
                {item.label}
              </Link>
            ))}
            <div className="mt-2 border-t border-slate-200 pt-4">
              <GoogleLoginButton />
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}

export default function Navbar() {
  const location = useLocation();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!isMobileMenuOpen) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isMobileMenuOpen]);

  return (
    <>
      <nav className="sticky top-0 z-50 border-b border-white/70 bg-white/80 backdrop-blur-xl">
        <div className="page-container">
          <div className="flex h-16 items-center justify-between">
            <Link to="/" className="flex items-center space-x-3 transition duration-200 hover:-translate-y-0.5">
              <img src={logo} alt="國立中央大學科系探索平台" className="h-10 w-10 object-contain" />
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
              <GoogleLoginButton />
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
        </div>
      </nav>

      {isMobileMenuOpen ? (
        <MobileMenuOverlay pathname={location.pathname} onClose={() => setIsMobileMenuOpen(false)} />
      ) : null}
    </>
  );
}
