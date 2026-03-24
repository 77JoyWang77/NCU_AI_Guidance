import { ReactNode } from 'react';
import Navbar from './Navbar';

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <main className="container mx-auto px-4 py-8">
        {children}
      </main>
      <footer className="border-t border-gray-200 mt-20 py-8 bg-white">
        <div className="container mx-auto px-4 text-center text-gray-600">
          <p>© 2026 中央大學高中生科系探索平台</p>
        </div>
      </footer>
    </div>
  );
}
