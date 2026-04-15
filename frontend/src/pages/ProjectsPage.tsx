import { useEffect, useMemo, useState } from 'react';
import { projectAPI } from '../api/services';
import type { Project } from '../types';
import { HiAcademicCap, HiArrowLeft, HiChat, HiPaperAirplane, HiUser } from 'react-icons/hi';
import PdfViewer from '../components/PdfViewer';

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [viewMode, setViewMode] = useState<'outline' | 'pdf-chat'>('outline');
  const [chatMessages, setChatMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [filterYear, setFilterYear] = useState('');
  const [filterDept, setFilterDept] = useState('');

  useEffect(() => {
    const loadProjects = async () => {
      try {
        const data = await projectAPI.getProjects();
        setProjects(data);
      } catch (error) {
        console.error('Failed to load projects:', error);
      }
    };

    loadProjects();
  }, []);

  const years = useMemo(() => [...new Set(projects.map((project) => project.year))].sort((a, b) => b.localeCompare(a)), [projects]);
  const departments = useMemo(() => [...new Set(projects.map((project) => project.department))].sort((a, b) => a.localeCompare(b, 'zh-Hant')), [projects]);

  const filteredProjects = useMemo(
    () =>
      projects.filter(
        (project) => (!filterYear || project.year === filterYear) && (!filterDept || project.department === filterDept)
      ),
    [projects, filterYear, filterDept]
  );

  const handleSelectProject = (project: Project) => {
    setSelectedProject(project);
    setChatMessages([
      {
        role: 'assistant',
        content: `你現在正在查看「${project.title}」。如果你想了解研究方向、內容重點或延伸問題，可以直接在右側對話。`,
      },
    ]);
  };

  const handleSendMessage = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!inputMessage.trim() || !selectedProject) return;

    const userMessage = inputMessage.trim();
    setChatMessages((prev) => [...prev, { role: 'user', content: userMessage }]);
    setInputMessage('');
    setChatLoading(true);

    try {
      const reply = await projectAPI.chatWithProject(selectedProject.id, userMessage);
      setChatMessages((prev) => [...prev, { role: 'assistant', content: reply }]);
    } catch (error) {
      console.error('Project chat failed:', error);
      setChatMessages((prev) => [...prev, { role: 'assistant', content: '目前無法取得回覆，請稍後再試一次。' }]);
    } finally {
      setChatLoading(false);
    }
  };

  const getTypeLabel = (type: string) => {
    switch (type) {
      case 'E':
        return '工程';
      case 'H':
        return '人文';
      case 'M':
        return '管理';
      case 'B':
        return '生醫';
      default:
        return type;
    }
  };

  const getTypeBadgeClass = (type: string) => {
    switch (type) {
      case 'E':
        return 'bg-blue-100 text-blue-800';
      case 'H':
        return 'bg-purple-100 text-purple-800';
      case 'M':
        return 'bg-green-100 text-green-800';
      case 'B':
        return 'bg-amber-100 text-amber-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const getPdfUrl = (project: Project): string => {
    if (project.pdfUrl) return project.pdfUrl;
    if (!project.pdfPath) return '';
    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const baseUrl = apiUrl.replace('/api', '');
    const encodedPath = project.pdfPath.split('\\').map(encodeURIComponent).join('/');
    return `${baseUrl}/pdfs/${encodedPath}`;
  };

  return (
    <div className="page-container flex h-full flex-col py-3">
      {viewMode !== 'pdf-chat' ? (
        <div className="mb-3 flex flex-shrink-0 items-center justify-between">
          <div className="flex items-center gap-2">
            <h1 className="text-base font-bold text-primary-900">研究計畫</h1>
            <span className="text-sm text-gray-400">/</span>
            <span className="text-sm text-gray-500">探索歷年專題成果，並進一步查看 PDF 或進行 AI 對話</span>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={filterYear}
              onChange={(event) => setFilterYear(event.target.value)}
              className="rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500"
            >
              <option value="">全部年度</option>
              {years.map((year) => (
                <option key={year} value={year}>
                  {year}
                </option>
              ))}
            </select>
            <select
              value={filterDept}
              onChange={(event) => setFilterDept(event.target.value)}
              className="max-w-[180px] rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500"
            >
              <option value="">全部系所</option>
              {departments.map((department) => (
                <option key={department} value={department}>
                  {department}
                </option>
              ))}
            </select>
            <span className="shrink-0 text-sm text-gray-500">
              共 <span className="font-semibold text-primary-700">{filteredProjects.length}</span> 筆
            </span>
          </div>
        </div>
      ) : null}

      {viewMode === 'outline' ? (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="flex min-h-0 flex-col">
            <div className="flex-1 space-y-2 overflow-y-auto">
              {filteredProjects.map((project) => (
                <div
                  key={project.id}
                  className={`card-interactive cursor-pointer p-4 ${
                    selectedProject?.id === project.id ? 'ring-2 ring-primary-600' : ''
                  }`}
                  onClick={() => handleSelectProject(project)}
                >
                  <div className="mb-2 flex items-start justify-between">
                    <span className={`badge text-xs ${getTypeBadgeClass(project.type)}`}>{getTypeLabel(project.type)}</span>
                    <span className="text-xs text-gray-500">{project.year}</span>
                  </div>
                  <h3 className="mb-2 line-clamp-2 text-sm font-semibold leading-tight text-primary-900">{project.title}</h3>
                  <div className="space-y-1 text-xs text-gray-600">
                    <div className="flex items-center">
                      <HiUser className="mr-1 h-3 w-3" />
                      <span>{project.studentName}</span>
                    </div>
                    <div className="flex items-center">
                      <HiAcademicCap className="mr-1 h-3 w-3" />
                      <span className="line-clamp-1">{project.department}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="min-h-0 overflow-y-auto lg:col-span-2">
            {selectedProject ? (
              <div className="card relative p-8">
                <div className="mb-6">
                  <div className="mb-4 flex items-start justify-between">
                    <span className={`badge ${getTypeBadgeClass(selectedProject.type)}`}>{getTypeLabel(selectedProject.type)}</span>
                    <span className="text-sm text-gray-500">{selectedProject.year}</span>
                  </div>
                  <h2 className="mb-3 text-2xl font-bold text-primary-900">{selectedProject.title}</h2>
                  <div className="flex items-center gap-4 text-sm text-gray-600">
                    <div className="flex items-center">
                      <HiUser className="mr-1 h-4 w-4" />
                      <span>{selectedProject.studentName}</span>
                    </div>
                    <div className="flex items-center">
                      <HiAcademicCap className="mr-1 h-4 w-4" />
                      <span>{selectedProject.department}</span>
                    </div>
                  </div>
                </div>

                <div className="mb-8 space-y-6">
                  <SectionBlock title="研究方向說明">
                    這份研究計畫來自「{selectedProject.department}」相關領域，內容可作為理解學系專業方向、問題意識與實作成果的參考。
                  </SectionBlock>
                  <SectionBlock title="閱讀方式建議">
                    建議先看題目與研究摘要，再留意方法、資料來源與結論。這樣可以更快掌握該學系在大學端可能接觸的研究形式。
                  </SectionBlock>
                  <SectionBlock title="延伸提問方向">
                    你可以進一步問 AI：「這份研究偏哪個領域？」「適合對哪些主題有興趣的人？」「和某個學系的課程有什麼關聯？」。
                  </SectionBlock>
                </div>

                <div className="flex justify-end">
                  <button onClick={() => setViewMode('pdf-chat')} className="btn-primary flex items-center gap-2">
                    <HiChat className="h-5 w-5" />
                    查看 PDF 與 AI 對話
                  </button>
                </div>
              </div>
            ) : (
              <div className="card flex h-full flex-col items-center justify-center">
                <HiChat className="mb-4 h-16 w-16 text-gray-300" />
                <p className="mb-2 text-gray-600">請先從左側選擇一項研究計畫。</p>
                <p className="text-sm text-gray-500">選擇後即可查看計畫介紹，並進一步進入 PDF 與對話模式。</p>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="card flex h-full flex-col overflow-hidden">
            <div className="flex flex-shrink-0 items-center gap-2 border-b border-gray-200 px-4 py-2.5">
              <button
                onClick={() => setViewMode('outline')}
                className="flex items-center gap-1 text-sm text-primary-600 transition-colors hover:text-primary-800"
              >
                <HiArrowLeft className="h-4 w-4" />
                返回介紹
              </button>
              <span className="text-gray-300">|</span>
              <span className="truncate text-sm font-medium text-gray-700">{selectedProject?.title}</span>
            </div>
            <div className="flex-1 overflow-hidden">
              {selectedProject?.pdfPath ? (
                <PdfViewer pdfUrl={getPdfUrl(selectedProject)} projectTitle={selectedProject.title} hideTitle />
              ) : (
                <div className="flex h-full items-center justify-center">
                  <div className="text-center text-gray-500">
                    <p className="mb-2 text-lg">目前沒有可顯示的 PDF</p>
                    <p className="text-sm">這份研究計畫尚未提供 PDF 檔案。</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="card flex h-full flex-col">
            <div className="flex flex-shrink-0 items-center gap-2 border-b border-gray-200 px-4 py-2.5">
              <h2 className="text-sm font-semibold text-gray-800">AI 對話區</h2>
              <span className="text-xs text-gray-400">你可以針對這份研究計畫提出問題</span>
            </div>

            <div className="flex-1 space-y-3 overflow-y-auto p-4">
              {chatMessages.map((message, index) => (
                <div key={index} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[80%] rounded-lg p-4 ${
                      message.role === 'user' ? 'bg-primary-700 text-white' : 'bg-gray-100 text-gray-900'
                    }`}
                  >
                    <p className="text-sm leading-relaxed">{message.content}</p>
                  </div>
                </div>
              ))}
              {chatLoading ? (
                <div className="flex justify-start">
                  <div className="rounded-lg bg-gray-100 p-4 text-gray-900">
                    <div className="flex space-x-2">
                      <div className="h-2 w-2 animate-bounce rounded-full bg-gray-400"></div>
                      <div className="h-2 w-2 animate-bounce rounded-full bg-gray-400 delay-100"></div>
                      <div className="h-2 w-2 animate-bounce rounded-full bg-gray-400 delay-200"></div>
                    </div>
                  </div>
                </div>
              ) : null}
            </div>

            <form onSubmit={handleSendMessage} className="border-t border-gray-200 p-3">
              <div className="flex gap-3">
                <input
                  type="text"
                  value={inputMessage}
                  onChange={(event) => setInputMessage(event.target.value)}
                  placeholder="輸入你想了解的研究問題..."
                  className="flex-1 rounded-md border border-gray-300 px-4 py-3 transition-colors focus:border-primary-500 focus:ring-2 focus:ring-primary-500"
                />
                <button type="submit" disabled={chatLoading || !inputMessage.trim()} className="btn-primary">
                  <HiPaperAirplane className="h-5 w-5" />
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function SectionBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="mb-3 flex items-center text-lg font-semibold text-primary-900">
        <span className="mr-3 h-6 w-1 bg-primary-600"></span>
        {title}
      </h3>
      <p className="pl-4 leading-relaxed text-gray-700">{children}</p>
    </div>
  );
}
