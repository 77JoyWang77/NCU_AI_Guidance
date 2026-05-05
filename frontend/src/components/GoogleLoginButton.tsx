import { useState } from 'react';
import { useAuth } from '../auth/AuthContext';

export default function GoogleLoginButton() {
  const { user, loading, loginWithGoogle, logout } = useAuth();
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
    return <span className="text-xs text-slate-400">登入中...</span>;
  }

  if (user) {
    return (
      <div className="flex items-center gap-2">
        {user.picture ? (
          <img src={user.picture} alt="" className="h-8 w-8 rounded-full object-cover" />
        ) : null}
        <span className="max-w-32 truncate text-xs font-medium text-slate-600">{user.name}</span>
        <button
          type="button"
          onClick={logout}
          className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 shadow-sm transition hover:bg-slate-50 hover:text-slate-900"
        >
          登出
        </button>
      </div>
    );
  }

  if (error) {
    return <span className="text-xs text-red-500">{error}</span>;
  }

  return (
    <button
      type="button"
      onClick={handleLogin}
      className="inline-flex rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 shadow-sm transition hover:bg-slate-50 hover:text-slate-900"
    >
      Google 登入
    </button>
  );
}
