import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { HiArrowRight, HiSearch, HiX } from 'react-icons/hi';

const SEARCH_ROUTES = [
  { label: '首頁', keywords: ['首頁', 'home', '平台'], path: '/' },
  { label: '興趣量表', keywords: ['興趣量表', '測評', 'assessment'], path: '/assessment' },
  { label: '課程資訊', keywords: ['課程資訊', '課程', 'courses'], path: '/courses' },
  { label: '課程搜尋', keywords: ['課程搜尋', '搜尋', 'chat'], path: '/course-search' },
  { label: '研究計畫', keywords: ['研究計畫', '專題', 'project'], path: '/projects' },
  { label: '資源連結', keywords: ['資源連結', '資源', '升學', 'resource'], path: '/resources' },
];

export default function FloatingSearch() {
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');

  const matchedRoutes = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return [];

    return SEARCH_ROUTES.filter(
      (route) =>
        route.label.toLowerCase().includes(normalized) ||
        route.keywords.some((keyword) => keyword.toLowerCase().includes(normalized) || normalized.includes(keyword.toLowerCase()))
    ).slice(0, 4);
  }, [query]);

  const handleNavigate = (path: string) => {
    setIsOpen(false);
    setQuery('');
    setError('');
    navigate(path);
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!query.trim()) return;

    const first = matchedRoutes[0];
    if (first) {
      handleNavigate(first.path);
      return;
    }

    setError('找不到符合的頁面，請試試其他關鍵字。');
  };

  return (
    <div className="fixed bottom-5 right-5 z-[70] flex flex-col items-end gap-3">
      {isOpen ? (
        <div className="route-fade-enter w-[320px] max-w-[calc(100vw-2rem)] rounded-2xl border border-white/70 bg-white/95 p-4 shadow-strong backdrop-blur">
          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 focus-within:border-primary-300 focus-within:bg-white">
              <HiSearch className="h-5 w-5 text-slate-400" />
              <input
                autoFocus
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setError('');
                }}
                placeholder="搜尋頁面，例如課程資訊、研究計畫"
                className="w-full bg-transparent text-sm text-slate-700 outline-none placeholder:text-slate-400"
              />
              <button
                type="button"
                onClick={() => {
                  setIsOpen(false);
                  setQuery('');
                  setError('');
                }}
                className="rounded-lg p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
                aria-label="關閉搜尋"
              >
                <HiX className="h-4 w-4" />
              </button>
            </div>

            {matchedRoutes.length > 0 ? (
              <div className="space-y-2">
                {matchedRoutes.map((route) => (
                  <button
                    key={route.path}
                    type="button"
                    onClick={() => handleNavigate(route.path)}
                    className="flex w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-3 py-2 text-left text-sm text-slate-700 transition duration-200 hover:-translate-y-0.5 hover:border-primary-200 hover:shadow-medium active:translate-y-0"
                  >
                    <div>
                      <div className="font-medium text-slate-900">{route.label}</div>
                      <div className="text-xs text-slate-500">{route.keywords.slice(0, 3).join(' / ')}</div>
                    </div>
                    <HiArrowRight className="h-4 w-4 text-primary-600" />
                  </button>
                ))}
              </div>
            ) : null}

            {error ? <p className="text-xs text-rose-600">{error}</p> : null}
          </form>
        </div>
      ) : null}

      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className={`flex h-14 w-14 items-center justify-center rounded-full border border-slate-200/60 bg-white/90 backdrop-blur-md shadow-md transition-all duration-300 hover:-translate-y-1 hover:shadow-lg active:translate-y-0 active:scale-95 ${isOpen ? 'text-indigo-600 bg-indigo-50/90' : 'text-slate-500 hover:text-indigo-500 hover:bg-slate-50/90'}`}
        aria-label={isOpen ? '收合搜尋' : '快速搜尋'}
        title={isOpen ? '收合搜尋' : '快速搜尋'}
      >
        {isOpen ? <HiX className="h-6 w-6" /> : <HiSearch className="h-6 w-6" />}
      </button>
    </div>
  );
}
