import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  HiAcademicCap,
  HiArrowRight,
  HiBookOpen,
  HiChartBar,
  HiChevronLeft,
  HiChevronRight,
  HiCollection,
  HiSearch,
} from 'react-icons/hi';

function CountUp({ value, suffix = '' }: { value: number; suffix?: string }) {
  const [displayValue, setDisplayValue] = useState(0);

  useEffect(() => {
    let frameId = 0;
    let start: number | null = null;
    const duration = 1200;

    const tick = (timestamp: number) => {
      if (!start) start = timestamp;
      const progress = Math.min((timestamp - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplayValue(Math.round(value * eased));
      if (progress < 1) frameId = window.requestAnimationFrame(tick);
    };

    frameId = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frameId);
  }, [value]);

  return (
    <>
      {displayValue.toLocaleString()}
      {suffix}
    </>
  );
}

const stats = [
  {
    value: 28,
    suffix: '',
    label: '學系總覽',
    description: '涵蓋中央大學主要學院與學系，幫助高中生快速建立完整的選系視野。',
  },
  {
    value: 1300,
    suffix: '+',
    label: '課程資料',
    description: '整理不同系所課程資訊，方便比較修課方向與學習內容差異。',
  },
  {
    value: 459,
    suffix: '',
    label: '研究計畫',
    description: '收錄歷年專題與研究成果，讓你提早看見大學端的學習樣貌。',
  },
];

const features = [
  {
    title: '興趣測評',
    description: '透過問答探索個人興趣與能力傾向，快速找到更適合自己的學系方向。',
    icon: HiChartBar,
    path: '/assessment',
    tag: '40+ 題目',
  },
  {
    title: '課程資訊',
    description: '瀏覽各系課程內容、學分與授課資訊，建立對不同學群的具體想像。',
    icon: HiBookOpen,
    path: '/courses',
    tag: '1,300+ 課程',
  },
  {
    title: '課程搜尋',
    description: '用關鍵字快速查找課程與教師資訊，縮短探索課程方向的時間。',
    icon: HiSearch,
    path: '/course-search',
    tag: '快速查找',
  },
  {
    title: '研究計畫',
    description: '從歷年研究與專題成果中，看見不同學系的延伸發展與實作面向。',
    icon: HiAcademicCap,
    path: '/projects',
    tag: '459 筆資料',
  },
  {
    title: '資源連結',
    description: '整合升學、學習與延伸閱讀資源，讓後續查找資訊更有效率。',
    icon: HiCollection,
    path: '/resources',
    tag: '整合入口',
  },
];

export default function HomePage() {
  const navigate = useNavigate();
  const [isLeaving, setIsLeaving] = useState(false);
  const [activeFeatureIndex, setActiveFeatureIndex] = useState(0);
  const featureSectionRef = useRef<HTMLElement | null>(null);
  const dragStateRef = useRef({ isDown: false, startX: 0, moved: false });

  const navigateWithAnimation = (path: string) => {
    setIsLeaving(true);
    window.setTimeout(() => {
      navigate(path);
      setIsLeaving(false);
    }, 220);
  };

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!dragStateRef.current.isDown) {
        setActiveFeatureIndex((prev) => (prev + 1) % features.length);
      }
    }, 4500);

    return () => window.clearInterval(timer);
  }, []);

  const goToFeature = (index: number) => {
    const total = features.length;
    setActiveFeatureIndex((index + total) % total);
  };

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    dragStateRef.current = {
      isDown: true,
      startX: event.clientX,
      moved: false,
    };
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragStateRef.current.isDown) return;
    const delta = event.clientX - dragStateRef.current.startX;
    if (Math.abs(delta) > 20) dragStateRef.current.moved = true;
  };

  const handlePointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragStateRef.current.isDown) return;
    const delta = event.clientX - dragStateRef.current.startX;
    const moved = dragStateRef.current.moved;
    dragStateRef.current.isDown = false;

    if (delta <= -40) goToFeature(activeFeatureIndex + 1);
    if (delta >= 40) goToFeature(activeFeatureIndex - 1);

    window.setTimeout(() => {
      dragStateRef.current.moved = false;
    }, 0);

    if (!moved && Math.abs(delta) < 10) return;
  };

  const handleFeatureClick = (path: string) => {
    if (dragStateRef.current.moved) return;
    navigateWithAnimation(path);
  };

  return (
    <div className={`transition duration-300 ${isLeaving ? 'translate-y-2 opacity-0' : 'translate-y-0 opacity-100'}`}>
      <section className="px-2 py-14 md:px-6 md:py-20">
        <div className="mx-auto max-w-5xl text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/90 px-4 py-2 text-sm font-medium text-slate-700 shadow-soft">
            <HiCollection className="h-4 w-4 text-primary-700" />
            國立中央大學科系探索平台
          </div>
          <h1 className="mt-6 text-4xl font-bold tracking-tight text-slate-950 md:text-6xl">
            用更清楚的資訊，
            <br className="hidden sm:block" />
            找到更適合你的科系方向。
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-base leading-7 text-slate-600 md:text-lg">
            以簡潔、清楚的方式整合興趣測評、課程資料、研究計畫與升學資源，
            幫助高中生更有方向地探索中央大學。
          </p>
          <div className="mt-10 flex flex-col justify-center gap-4 sm:flex-row">
            <button type="button" onClick={() => navigateWithAnimation('/assessment')} className="btn-primary">
              開始測評
              <HiArrowRight className="ml-2 h-5 w-5" />
            </button>
            <button
              type="button"
              onClick={() => featureSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
              className="btn-secondary"
            >
              查看平台功能
            </button>
          </div>
        </div>
      </section>

      <section ref={featureSectionRef} className="py-16">
        <div className="mb-8 text-center">
          <p className="text-sm font-medium uppercase tracking-[0.22em] text-slate-500">Core Modules</p>
          <h2 className="mt-2 text-3xl font-semibold text-slate-950">平台功能</h2>
          <p className="mx-auto mt-3 max-w-2xl text-sm leading-6 text-slate-600">
            你可以用滑鼠左右拖動切換卡片，也能直接點擊主卡跳轉到對應功能頁面。
          </p>
        </div>

        <div
          className="feature-coverflow"
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
        >
          <div className="feature-coverflow-stage">
            {features.map((feature, index) => {
              const Icon = feature.icon;
              const offset = index - activeFeatureIndex;
              const wrappedOffset =
                offset > features.length / 2 ? offset - features.length : offset < -features.length / 2 ? offset + features.length : offset;

              let positionClass = 'feature-coverflow-hidden';
              if (wrappedOffset === 0) positionClass = 'feature-coverflow-center';
              if (wrappedOffset === -1) positionClass = 'feature-coverflow-left';
              if (wrappedOffset === 1) positionClass = 'feature-coverflow-right';
              if (wrappedOffset === -2) positionClass = 'feature-coverflow-far-left';
              if (wrappedOffset === 2) positionClass = 'feature-coverflow-far-right';

              return (
                <button
                  key={feature.title}
                  type="button"
                  onClick={() => (wrappedOffset === 0 ? handleFeatureClick(feature.path) : goToFeature(index))}
                  className={`feature-coverflow-card ${positionClass}`}
                >
                  <div className="card-interactive feature-coverflow-card-inner min-h-[232px] rounded-3xl p-6 text-left">
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-primary-700">
                      <Icon className="h-6 w-6" />
                    </div>
                    <div className="mt-5 flex items-center justify-between gap-4">
                      <h3 className="text-lg font-semibold text-slate-950">{feature.title}</h3>
                      <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">{feature.tag}</span>
                    </div>
                    <p className="feature-card-description mt-3 text-sm leading-6 text-slate-600">{feature.description}</p>
                    <div className="mt-6 inline-flex items-center text-sm font-medium text-primary-700">
                      前往功能
                      <HiArrowRight className="ml-2 h-4 w-4" />
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          <div className="mt-[2px] flex items-center justify-center gap-2">
            <button
              type="button"
              onClick={() => goToFeature(activeFeatureIndex - 1)}
              className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-slate-200 bg-white/90 text-slate-600 shadow-soft transition hover:bg-white hover:text-slate-900"
              aria-label="上一張"
            >
              <HiChevronLeft className="h-5 w-5" />
            </button>
            <button
              type="button"
              onClick={() => goToFeature(activeFeatureIndex + 1)}
              className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-slate-200 bg-white/90 text-slate-600 shadow-soft transition hover:bg-white hover:text-slate-900"
              aria-label="下一張"
            >
              <HiChevronRight className="h-5 w-5" />
            </button>
          </div>
        </div>
      </section>

      <section className="pb-6">
        <div className="card rounded-[2rem] border-white/70 bg-white/78 p-8 shadow-soft backdrop-blur md:p-10">
          <div className="flex flex-col items-center gap-4 text-center">
            <div>
              <p className="text-sm font-medium uppercase tracking-[0.22em] text-slate-500">Platform Data</p>
              <h2 className="mt-2 text-3xl font-semibold text-slate-950">平台數據</h2>
            </div>
          </div>

          <div className="mt-10 grid gap-6 md:grid-cols-3">
            {stats.map((stat) => (
              <div key={stat.label} className="rounded-3xl border border-slate-200 bg-slate-50/70 p-6 text-center">
                <div className="text-4xl font-bold tracking-tight text-primary-900 md:text-5xl">
                  <CountUp value={stat.value} suffix={stat.suffix} />
                </div>
                <div className="mt-3 text-sm font-semibold text-slate-700">{stat.label}</div>
                <p className="mt-2 text-sm leading-6 text-slate-500">{stat.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
