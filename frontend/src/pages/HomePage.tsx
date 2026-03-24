import { Link } from 'react-router-dom';
import { HiChartBar, HiBookOpen, HiSearch, HiAcademicCap, HiArrowRight } from 'react-icons/hi';

export default function HomePage() {
  const features = [
    {
      title: '科系興趣量表',
      description: '透過專業測評，協助你探索適合的科系方向',
      icon: HiChartBar,
      link: '/assessment',
      stats: '40+ 題目',
    },
    {
      title: '課程資訊',
      description: '完整的中央大學課程資料庫與詳細資訊',
      icon: HiBookOpen,
      link: '/courses',
      stats: '1,300+ 課程',
    },
    {
      title: '智慧搜尋',
      description: '快速搜尋並找到感興趣的課程內容',
      icon: HiSearch,
      link: '/course-search',
      stats: '即時搜尋',
    },
    {
      title: '研究計畫',
      description: '瀏覽歷年大專生研究計畫，了解科系研究方向',
      icon: HiAcademicCap,
      link: '/projects',
      stats: '459 個計畫',
    },
  ];

  return (
    <div className="page-container">
      {/* Hero Section */}
      <section className="py-16 md:py-24">
        <div className="text-center max-w-4xl mx-auto">
          <div className="inline-block px-4 py-2 bg-primary-50 text-primary-700 rounded-full text-sm font-medium mb-6">
            國立中央大學
          </div>
          <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold text-primary-900 mb-6 leading-tight">
            科系探索平台
          </h1>
          <p className="text-lg md:text-xl text-gray-600 mb-10 leading-relaxed">
            為高中生提供完整的科系資訊與測評工具<br className="hidden sm:block" />
            協助你找到最適合的大學科系
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link to="/assessment" className="btn-primary">
              開始測評
              <HiArrowRight className="ml-2 w-5 h-5" />
            </Link>
            <Link to="/courses" className="btn-secondary">
              瀏覽課程
            </Link>
          </div>
        </div>
      </section>

      {/* Features Grid */}
      <section className="py-16 border-t border-gray-200">
        <h2 className="section-title text-center">平台功能</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 lg:gap-8">
          {features.map((feature) => {
            const IconComponent = feature.icon;
            return (
              <Link
                key={feature.title}
                to={feature.link}
                className="card-interactive p-8"
              >
                <div className="flex items-start space-x-4">
                  <div className="flex-shrink-0">
                    <div className="w-12 h-12 bg-primary-100 rounded-lg flex items-center justify-center">
                      <IconComponent className="w-6 h-6 text-primary-700" />
                    </div>
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-xl font-bold text-primary-900 mb-2">
                      {feature.title}
                    </h3>
                    <p className="text-gray-600 mb-3 leading-relaxed">
                      {feature.description}
                    </p>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-primary-600 font-medium">
                        {feature.stats}
                      </span>
                      <HiArrowRight className="w-5 h-5 text-primary-600" />
                    </div>
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      </section>

      {/* Stats Section */}
      <section className="py-16">
        <div className="card p-10">
          <h2 className="text-2xl font-bold text-primary-900 text-center mb-10">
            平台資料統計
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="text-center">
              <div className="text-4xl font-bold text-primary-700 mb-2">38</div>
              <div className="text-gray-600 font-medium">個科系</div>
            </div>
            <div className="text-center border-l border-r border-gray-200">
              <div className="text-4xl font-bold text-primary-700 mb-2">1,300+</div>
              <div className="text-gray-600 font-medium">門課程</div>
            </div>
            <div className="text-center">
              <div className="text-4xl font-bold text-primary-700 mb-2">459</div>
              <div className="text-gray-600 font-medium">個研究計畫</div>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-16 bg-primary-900 -mx-4 sm:-mx-6 lg:-mx-8 px-4 sm:px-6 lg:px-8 rounded-xl">
        <div className="text-center max-w-2xl mx-auto">
          <h2 className="text-3xl font-bold text-white mb-4">
            準備好開始探索了嗎？
          </h2>
          <p className="text-primary-100 mb-8 text-lg">
            透過科系興趣量表，找到最適合你的未來方向
          </p>
          <Link
            to="/assessment"
            className="inline-flex items-center px-8 py-4 text-lg font-medium text-primary-900 bg-white rounded-md hover:bg-gray-50 transition-colors"
          >
            立即開始
            <HiArrowRight className="ml-2 w-5 h-5" />
          </Link>
        </div>
      </section>
    </div>
  );
}
