import { useMemo, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import FloatingSearch from './FloatingSearch';
import Navbar from './Navbar';

interface LayoutProps {
  fullHeight?: boolean;
}

const BACKGROUND_THEMES = [
  'bg-theme-1',
  'bg-theme-2',
  'bg-theme-3',
  'bg-theme-4',
  'bg-theme-5',
  'bg-theme-6',
  'bg-theme-7',
  'bg-theme-8',
  'bg-theme-9',
  'bg-theme-10',
];

export default function Layout({ fullHeight = false }: LayoutProps) {
  const location = useLocation();
  const [backgroundIndex, setBackgroundIndex] = useState(0);
  const backgroundClass = useMemo(() => BACKGROUND_THEMES[backgroundIndex % BACKGROUND_THEMES.length], [backgroundIndex]);
  const isHome = location.pathname === '/';

  const handleBackgroundClick = (event: React.MouseEvent<HTMLElement>) => {
    if (event.target !== event.currentTarget) return;
    setBackgroundIndex((prev) => (prev + 1) % BACKGROUND_THEMES.length);
  };

  return (
    <div
      className={`${backgroundClass} ${fullHeight ? 'flex h-screen flex-col overflow-hidden' : 'min-h-screen'} transition-colors duration-500`}
      onClick={handleBackgroundClick}
    >
      <Navbar />
      <main className={fullHeight ? 'flex-1 overflow-hidden' : 'page-container py-8'} onClick={handleBackgroundClick}>
        <div key={location.pathname} className="page-animate h-full">
          <Outlet />
        </div>
      </main>
      {isHome ? (
        <footer className="mt-20 border-t border-white/70 bg-white/75 py-8 backdrop-blur">
          <div className="page-container text-center text-sm text-slate-600">
            <p>© 2026 國立中央大學科系探索平台</p>
          </div>
        </footer>
      ) : null}
      <FloatingSearch />
    </div>
  );
}
