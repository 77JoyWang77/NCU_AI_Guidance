import { HiAcademicCap, HiCollection, HiExternalLink } from 'react-icons/hi';

const scoreResources = [
  {
    title: '114大學交叉查榜｜www.com.tw',
    description: '查詢大學申請、繁星、分科與統測榜單，也可查看各系組錄取分數與交叉查榜資訊。',
    href: 'https://www.com.tw/cross/',
  },
  {
    title: '大學甄選入學委員會',
    description: '查詢大學申請入學與繁星推薦的官方招生簡章、重要時程、校系分則與錄取公告。',
    href: 'https://www.uac.edu.tw/',
  },
  {
    title: '1111落點分析',
    description: '輸入成績後進行校系落點分析，搭配學群、志願與升學建議評估可能錄取範圍。',
    href: 'https://exam-match.1111.com.tw/',
  },
];

const studyResources = [
  {
    title: 'ColleGo!',
    description: '探索大學學群、學類、校系與高中學習準備方向，適合用來認識科系與規劃學習路徑。',
    href: 'https://collego.edu.tw/',
  },
  {
    title: 'IOH 開放個人經驗平台',
    description: '透過學長姐與講者的求學、科系、職涯經驗分享，了解不同校系的實際學習樣貌。',
    href: 'https://ioh.tw/',
  },
  {
    title: '大學問',
    description: '查詢大學校系、學群分類、入學管道與升學新聞，適合快速比較不同學校與科系資訊。',
    href: 'https://www.unews.com.tw/',
  },
];

const departmentGroups = [
  {
    college: '文學院',
    links: [
      ['文學院學士班', 'https://ipla.ncu.edu.tw/'],
      ['中國文學系', 'https://www.chinese.ncu.edu.tw/'],
      ['英美語文學系', 'https://english.ncu.edu.tw/'],
      ['法國語文學系', 'https://french.ncu.edu.tw/'],
    ],
  },
  {
    college: '理學院',
    links: [
      ['理學院學士班', 'https://www.science.ncu.edu.tw/'],
      ['化學學系', 'https://www.chem.ncu.edu.tw/'],
      ['物理學系', 'https://www.phy.ncu.edu.tw/'],
      ['數學系', 'https://w2.math.ncu.edu.tw/'],
      ['光電科學與工程學系', 'https://www.dop.ncu.edu.tw/'],
    ],
  },
  {
    college: '工學院',
    links: [
      ['工學院學士班', 'https://ipe.ec.ncu.edu.tw/'],
      ['土木工程學系', 'https://www.cv.ncu.edu.tw/'],
      ['機械工程學系光機電工程碩士班', 'https://www.cme.ncu.edu.tw/'],
      ['機械工程學系', 'https://www.me.ncu.edu.tw/'],
    ],
  },
  {
    college: '管理學院',
    links: [
      ['經濟學系', 'https://ec.mgt.ncu.edu.tw/'],
      ['企業管理學系', 'https://ba.mgt.ncu.edu.tw/'],
      ['財務金融學系', 'https://fm.mgt.ncu.edu.tw/'],
      ['資訊管理學系', 'https://im.mgt.ncu.edu.tw/'],
    ],
  },
  {
    college: '資訊電機學院',
    links: [
      ['資訊電機學院學士班', 'https://www.ipeecs.ncu.edu.tw/'],
      ['電機工程學系', 'https://www2.ee.ncu.edu.tw/'],
      ['資訊工程學系', 'https://www.csie.ncu.edu.tw/'],
      ['通訊工程學系', 'https://www.ce.ncu.edu.tw/'],
    ],
  },
  {
    college: '地球科學學院',
    links: [
      ['地球科學學院學士班', 'https://escollege.ncu.edu.tw/'],
      ['地球科學學系', 'https://www.gep.ncu.edu.tw/'],
      ['大氣科學學系', 'https://www.atm.ncu.edu.tw/'],
      ['太空科學與工程學系', 'https://www.ss.ncu.edu.tw/'],
    ],
  },
  {
    college: '客家學院',
    links: [['客家語文暨社會科學學系', 'https://hakka.ncu.edu.tw/']],
  },
  {
    college: '生醫理工學院',
    links: [
      ['生命科學系', 'https://nculs.in.ncu.edu.tw/'],
      ['生醫科學與工程學系', 'https://dbse.ncu.edu.tw/'],
    ],
  },
];

function ResourceCard({ title, description, href }: { title: string; description: string; href: string }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="card-interactive block rounded-3xl p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
          <p className="resource-card-description mt-2 text-sm leading-6 text-slate-600">{description}</p>
        </div>
        <div className="rounded-full bg-slate-100 p-2 text-primary-700">
          <HiExternalLink className="h-5 w-5" />
        </div>
      </div>
    </a>
  );
}

export default function ResourcesPage() {
  return (
    <div className="page-animate pb-12">
      <section className="py-16 md:py-20">
        <div className="max-w-3xl">
          <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/80 px-4 py-2 text-sm font-medium text-slate-700 shadow-soft">
            <HiCollection className="h-4 w-4 text-primary-700" />
            資源整理
          </div>
          <h1 className="mt-6 text-4xl font-bold tracking-tight text-slate-950 md:text-5xl">升學與校系資源</h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600 md:text-lg">
            這裡整理了落點分析工具、升學參考平台與中央大學各學院、系所官方網站，方便你快速查詢志願、校系資訊與延伸閱讀。
          </p>
        </div>
      </section>

      <section className="pb-12">
        <div className="mb-6 flex items-center gap-3">
          <div className="rounded-2xl bg-primary-100 p-2 text-primary-700">
            <HiExternalLink className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-2xl font-semibold text-slate-950">落點分析相關網站</h2>
            <p className="text-sm text-slate-500">查詢交叉查榜、招生簡章、錄取公告與成績落點分析工具。</p>
          </div>
        </div>
        <div className="grid gap-5 md:grid-cols-3">
          {scoreResources.map((resource) => (
            <ResourceCard key={resource.title} {...resource} />
          ))}
        </div>
      </section>

      <section className="pb-12">
        <div className="mb-6 flex items-center gap-3">
          <div className="rounded-2xl bg-primary-100 p-2 text-primary-700">
            <HiExternalLink className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-2xl font-semibold text-slate-950">升學參考平台</h2>
            <p className="text-sm text-slate-500">認識學群、學類、校系特色與學長姐經驗，輔助選系與生涯探索。</p>
          </div>
        </div>
        <div className="grid gap-5 md:grid-cols-3">
          {studyResources.map((resource) => (
            <ResourceCard key={resource.title} {...resource} />
          ))}
        </div>
      </section>

      <section className="pb-8">
        <div className="mb-6 flex items-center gap-3">
          <div className="rounded-2xl bg-primary-100 p-2 text-primary-700">
            <HiAcademicCap className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-2xl font-semibold text-slate-950">中央大學學院與系所</h2>
            <p className="text-sm text-slate-500">點選下方連結可前往各學院與系所官方網站。</p>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          {departmentGroups.map((group) => (
            <section key={group.college} className="card rounded-3xl p-6">
              <h3 className="text-lg font-semibold text-slate-950">{group.college}</h3>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {group.links.map(([label, href]) => (
                  <a
                    key={label}
                    href={href}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center justify-between rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 transition duration-200 hover:-translate-y-1 hover:border-primary-200 hover:bg-white hover:shadow-medium"
                  >
                    <span className="font-medium text-slate-900">{label}</span>
                    <HiExternalLink className="h-4 w-4 text-primary-600" />
                  </a>
                ))}
              </div>
            </section>
          ))}
        </div>
      </section>
    </div>
  );
}
