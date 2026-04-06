import { Outlet } from 'react-router-dom';
import Navbar from './Navbar';

interface LayoutProps {
  fullHeight?: boolean;
}

export default function Layout({ fullHeight = false }: LayoutProps) {
  return (
    <div className={`bg-gray-50 ${fullHeight ? 'h-screen flex flex-col overflow-hidden' : 'min-h-screen'}`}>
      <Navbar />
      <main className={fullHeight ? 'flex-1 overflow-hidden' : 'container mx-auto px-4 py-8'}>
        <Outlet />
      </main>
      {!fullHeight && (
        <footer className="border-t border-gray-200 mt-20 py-8 bg-white">
          <div className="container mx-auto px-4 text-center text-gray-600">
            <p>© 2026 中央大學高中生科系探索平台</p>
          </div>
        </footer>
      )}
    </div>
  );
}
