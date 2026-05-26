import { useState } from 'react';
import { Link } from 'react-router-dom';
import { HiUser } from 'react-icons/hi';
import { useAuth } from '../auth/AuthContext';

function GoogleMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4 shrink-0">
      <path fill="#4285F4" d="M21.6 12.2c0-.7-.1-1.3-.2-1.9H12v3.6h5.4c-.2 1.2-.9 2.3-2 3v2.4h3.2c1.9-1.7 3-4.2 3-7.1z" />
      <path fill="#34A853" d="M12 22c2.7 0 5-.9 6.6-2.5l-3.2-2.4c-.9.6-2 1-3.4 1-2.6 0-4.8-1.8-5.6-4.1H3.1v2.5C4.8 19.8 8.1 22 12 22z" />
      <path fill="#FBBC05" d="M6.4 14c-.2-.6-.3-1.3-.3-2s.1-1.4.3-2V7.5H3.1C2.4 8.9 2 10.4 2 12s.4 3.1 1.1 4.5L6.4 14z" />
      <path fill="#EA4335" d="M12 5.9c1.5 0 2.8.5 3.8 1.5l2.8-2.8C16.9 3 14.7 2 12 2 8.1 2 4.8 4.2 3.1 7.5L6.4 10c.8-2.3 3-4.1 5.6-4.1z" />
    </svg>
  );
}

export default function GoogleLoginButton() {
  const { user, loading, loginWithGoogle } = useAuth();
  const [error, setError] = useState('');

  const handleLogin = async () => {
    setError('');
    try {
      await loginWithGoogle();
    } catch {
      setError('登入失敗');
    }
  };

  if (loading) {
    return (
      <span className="nav-chip inline-flex items-center gap-1.5 text-slate-400">
        <GoogleMark />
        登入
      </span>
    );
  }

  if (user) {
    return (
      <Link
        to="/profile"
        className="flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 shadow-sm transition hover:border-primary-200 hover:bg-primary-50 hover:text-primary-700"
      >
        <HiUser className="h-5 w-5" />
      </Link>
    );
  }

  if (error) {
    return (
      <button
        type="button"
        onClick={handleLogin}
        className="nav-chip inline-flex items-center gap-1.5"
        title={error}
      >
        <GoogleMark />
        登入
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={handleLogin}
      className="nav-chip inline-flex items-center gap-1.5"
    >
      <GoogleMark />
      登入
    </button>
  );
}
