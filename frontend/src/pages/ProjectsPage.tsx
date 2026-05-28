import { useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  HiAcademicCap,
  HiArrowLeft,
  HiChat,
  HiChevronLeft,
  HiChevronRight,
  HiPaperAirplane,
  HiStop,
  HiUser,
} from 'react-icons/hi';
import { projectAPI } from '../api/services';
import PdfViewer from '../components/PdfViewer';
import type { Project } from '../types';

type ChatMessage = {
  role: 'user' | 'assistant';
  content: string;
};

type MobileOutlineView = 'list' | 'detail';

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [viewMode, setViewMode] = useState<'outline' | 'pdf-chat'>('outline');
  const [mobileOutlineView, setMobileOutlineView] = useState<MobileOutlineView>('list');
  const [isMobileChatOpen, setIsMobileChatOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [threadId, setThreadId] = useState<string | undefined>(undefined);
  const [streamingText, setStreamingText] = useState('');
  const abortCtrlRef = useRef<AbortController | null>(null);
  const streamingTextRef = useRef('');
  const [loading, setLoading] = useState(true);
  const [filterYear, setFilterYear] = useState('');
  const [filterDept, setFilterDept] = useState('');

  useEffect(() => {
    projectAPI
      .getProjects()
      .then((data) => {
        setProjects(data);
      })
      .catch((error) => {
        console.error('Failed to load projects:', error);
      })
      .finally(() => setLoading(false));
  }, []);

  const years = useMemo(
    () => [...new Set(projects.map((project) => project.year))].sort((a, b) => b.localeCompare(a)),
    [projects]
  );

  const departments = useMemo(
    () => [...new Set(projects.map((project) => project.department))].sort((a, b) => a.localeCompare(b, 'zh-Hant')),
    [projects]
  );

  const filteredProjects = useMemo(
    () =>
      projects.filter(
        (project) => (!filterYear || project.year === filterYear) && (!filterDept || project.department === filterDept)
      ),
    [projects, filterYear, filterDept]
  );

  const clearSelectedIfFiltered = (nextYear: string, nextDept: string) => {
    if (!selectedProject) return;
    const stillExists = projects.some(
      (p) =>
        p.id === selectedProject.id &&
        (!nextYear || p.year === nextYear) &&
        (!nextDept || p.department === nextDept),
    );
    if (stillExists) return;
    setSelectedProject(null);
    setChatMessages([]);
    setInputMessage('');
    setViewMode('outline');
    setMobileOutlineView('list');
    setIsMobileChatOpen(false);
  };

  const handleFilterYearChange = (year: string) => {
    setFilterYear(year);
    clearSelectedIfFiltered(year, filterDept);
  };

  const handleFilterDeptChange = (dept: string) => {
    setFilterDept(dept);
    clearSelectedIfFiltered(filterYear, dept);
  };

  const handleSelectProject = (project: Project) => {
    setSelectedProject(project);
    setChatMessages([createWelcomeMessage(project)]);
    setInputMessage('');
    setViewMode('outline');
    setMobileOutlineView('detail');
    setIsMobileChatOpen(false);
    setThreadId(undefined);
    streamingTextRef.current = '';
    setStreamingText('');
    abortCtrlRef.current?.abort();
    abortCtrlRef.current = null;
  };

  const handleBackToOutline = () => {
    setViewMode('outline');
    setMobileOutlineView('detail');
    setIsMobileChatOpen(false);
  };

  const handleBackToProjectList = () => {
    setMobileOutlineView('list');
  };

  const handleOpenPdfChat = () => {
    if (!selectedProject) return;
    setViewMode('pdf-chat');
    setIsMobileChatOpen(false);
    if (chatMessages.length === 0) {
      setChatMessages([createWelcomeMessage(selectedProject)]);
    }
  };

  const handleSendMessage = (event: FormEvent) => {
    event.preventDefault();
    if (!inputMessage.trim() || !selectedProject || chatLoading) return;

    const userMessage = inputMessage.trim();
    setChatMessages((prev) => [...prev, { role: 'user', content: userMessage }]);
    setInputMessage('');
    setChatLoading(true);
    setStreamingText('');

    const ctrl = projectAPI.streamChat(
      selectedProject.id,
      userMessage,
      {
        onToken: (token) => {
          streamingTextRef.current += token;
          setStreamingText(streamingTextRef.current);
        },
        onDone: (sessionId) => {
          const finalText = streamingTextRef.current;
          streamingTextRef.current = '';
          setStreamingText('');
          if (finalText) {
            setChatMessages((msgs) => [...msgs, { role: 'assistant', content: finalText }]);
          }
          setChatLoading(false);
          setThreadId(sessionId || undefined);
          abortCtrlRef.current = null;
        },
        onError: (msg) => {
          console.error('Project stream error:', msg);
          streamingTextRef.current = '';
          setStreamingText('');
          setChatMessages((prev) => [
            ...prev,
            { role: 'assistant', content: '目前暫時無法回應，請稍後再試一次。' },
          ]);
          setChatLoading(false);
          abortCtrlRef.current = null;
        },
      },
      threadId,
    );
    abortCtrlRef.current = ctrl;
  };

  const handleCancelStream = () => {
    if (!abortCtrlRef.current || !selectedProject || !threadId) return;
    abortCtrlRef.current.abort();
    abortCtrlRef.current = null;
    if (threadId) projectAPI.cancelChat(selectedProject.id, threadId).catch(() => {});
    const finalText = streamingTextRef.current;
    streamingTextRef.current = '';
    setStreamingText('');
    if (finalText) {
      setChatMessages((msgs) => [...msgs, { role: 'assistant', content: finalText + '…（已中止）' }]);
    }
    setChatLoading(false);
  };

  const getCollegeLabel = (department: string) => {
    const collegeByDepartment: Record<string, string> = {
      '文學院學士班': '文學院',
      '中國文學系': '文學院',
      '英美語文學系': '文學院',
      '法國語文學系': '文學院',
      '理學院學士班': '理學院',
      '化學學系': '理學院',
      '物理學系': '理學院',
      '數學系': '理學院',
      '光電科學與工程學系': '理學院',
      '光電科學研究中心': '理學院',
      '天文研究所': '理學院',
      '統計研究所': '理學院',
      '工學院學士班': '工學院',
      '土木工程學系': '工學院',
      '機械工程學系': '工學院',
      '化學工程與材料工程學系': '工學院',
      '材料科學與工程研究所': '工學院',
      '營建管理研究所': '工學院',
      '環境工程研究所': '工學院',
      '能源工程研究所': '工學院',
      '經濟學系': '管理學院',
      '企業管理學系': '管理學院',
      '財務金融學系': '管理學院',
      '資訊管理學系': '管理學院',
      '資訊電機學院學士班': '資訊電機學院',
      '電機工程學系': '資訊電機學院',
      '資訊工程學系': '資訊電機學院',
      '通訊工程學系': '資訊電機學院',
      '網路學習科技研究所': '資訊電機學院',
      '地球科學學院學士班': '地球科學學院',
      '地球科學學系': '地球科學學院',
      '大氣科學學系': '地球科學學院',
      '太空科學與工程學系': '地球科學學院',
      '太空及遙測研究中心': '地球科學學院',
      '太空科學與工程研究所': '地球科學學院',
      '太空科學與科技研究中心': '地球科學學院',
      '應用地質研究所': '地球科學學院',
      '水文與海洋科學研究所': '地球科學學院',
      '客家語文暨社會科學學系': '客家學院',
      '生命科學系': '生醫理工學院',
      '生醫科學與工程學系': '生醫理工學院',
      '系統生物與生物資訊研究所': '生醫理工學院',
      '認知神經科學研究所': '生醫理工學院',
    };

    return collegeByDepartment[department] || '未分類單位';
  };

  const getCollegeBadgeClass = (college: string) => {
    switch (college) {
      case '文學院':
        return 'bg-blue-100 text-blue-800';
      case '理學院':
        return 'bg-cyan-100 text-cyan-800';
      case '工學院':
        return 'bg-orange-100 text-orange-800';
      case '管理學院':
        return 'bg-green-100 text-green-800';
      case '資訊電機學院':
        return 'bg-indigo-100 text-indigo-800';
      case '地球科學學院':
        return 'bg-teal-100 text-teal-800';
      case '客家學院':
        return 'bg-rose-100 text-rose-800';
      case '生醫理工學院':
        return 'bg-pink-100 text-pink-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  const getPdfUrl = (project: Project) => {
    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const baseUrl = apiUrl.replace('/api', '');

    if (project.pdfUrl) {
      if (project.pdfUrl.startsWith('http://') || project.pdfUrl.startsWith('https://')) {
        return project.pdfUrl;
      }
      if (project.pdfUrl.startsWith('/')) {
        return `${baseUrl}${project.pdfUrl}`;
      }
      return project.pdfUrl;
    }

    if (!project.pdfPath) return '';
    const encodedPath = project.pdfPath.split('\\').map(encodeURIComponent).join('/');
    return `${baseUrl}/pdfs/${encodedPath}`;
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <div className="mx-auto mb-4 h-12 w-12 animate-spin rounded-full border-b-2 border-primary-600"></div>
          <p className="text-gray-600">正在載入研究計畫...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container flex h-full flex-col py-3">
      {viewMode !== 'pdf-chat' ? (
        <div className="mb-3 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 items-center gap-2">
            <h1 className="text-base font-bold text-primary-900">專題成果</h1>
            <span className="text-sm text-gray-400">/</span>
            <span className="text-sm text-gray-500">瀏覽歷年專題，並可進一步開啟 PDF 與 AI 問答。</span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={filterYear}
              onChange={(event) => handleFilterYearChange(event.target.value)}
              className="rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500"
            >
              <option value="">全部年份</option>
              {years.map((year) => (
                <option key={year} value={year}>
                  {year}
                </option>
              ))}
            </select>
            <select
              value={filterDept}
              onChange={(event) => handleFilterDeptChange(event.target.value)}
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
        <>
          <div className="flex min-h-0 flex-1 flex-col lg:hidden">
            {mobileOutlineView === 'detail' && selectedProject ? (
              <div className="card flex-1 overflow-y-auto p-6">
                <div className="mb-4">
                  <button
                    type="button"
                    onClick={handleBackToProjectList}
                    className="flex items-center gap-1 text-sm text-primary-600 transition-colors hover:text-primary-800"
                  >
                    <HiArrowLeft className="h-4 w-4" />
                    返回專題列表
                  </button>
                </div>

                <ProjectSummary
                  project={selectedProject}
                  getCollegeLabel={getCollegeLabel}
                  getCollegeBadgeClass={getCollegeBadgeClass}
                />

                <div className="mt-8 flex justify-end">
                  <button type="button" onClick={handleOpenPdfChat} className="btn-primary flex items-center gap-2">
                    <HiChat className="h-5 w-5" />
                    查看 PDF 與 AI 對話
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex min-h-0 flex-1 flex-col">
                <div className="flex-1 overflow-y-auto overflow-x-hidden [scrollbar-gutter:stable_both-edges]">
                  <div className="space-y-3 px-1 pt-2 pb-2 pr-4">
                    {filteredProjects.map((project) => (
                      <div
                        key={project.id}
                        className={`card cursor-pointer p-4 transition duration-200 ease-out hover:border-primary-200 hover:shadow-medium active:scale-[0.99] ${
                          selectedProject?.id === project.id ? 'border-primary-500 shadow-medium' : ''
                        }`}
                        onClick={() => handleSelectProject(project)}
                      >
                        <ProjectCardContent
                          project={project}
                          getCollegeLabel={getCollegeLabel}
                          getCollegeBadgeClass={getCollegeBadgeClass}
                        />
                      </div>
                    ))}
                    {filteredProjects.length === 0 ? (
                      <div className="card p-6 text-center text-sm text-gray-500">目前沒有符合條件的研究計畫。</div>
                    ) : null}
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="hidden min-h-0 flex-1 lg:grid lg:grid-cols-3 lg:gap-4">
            <div className="flex min-h-0 flex-col">
              <div className="flex-1 overflow-y-auto overflow-x-hidden [scrollbar-gutter:stable_both-edges]">
                <div className="space-y-3 px-1 pt-2 pb-2 pr-4">
                  {filteredProjects.map((project) => (
                    <div
                      key={project.id}
                      className={`card cursor-pointer p-4 transition duration-200 ease-out hover:border-primary-200 hover:shadow-medium active:scale-[0.99] ${
                        selectedProject?.id === project.id ? 'border-primary-500 shadow-medium' : ''
                      }`}
                      onClick={() => handleSelectProject(project)}
                    >
                      <ProjectCardContent
                        project={project}
                        getCollegeLabel={getCollegeLabel}
                        getCollegeBadgeClass={getCollegeBadgeClass}
                      />
                    </div>
                  ))}
                  {filteredProjects.length === 0 ? (
                    <div className="card p-6 text-center text-sm text-gray-500">目前沒有符合條件的研究計畫。</div>
                  ) : null}
                </div>
              </div>
            </div>

            <div className="min-h-0 overflow-y-auto lg:col-span-2">
              {selectedProject ? (
                <div className="card relative p-8">
                  <ProjectSummary
                    project={selectedProject}
                    getCollegeLabel={getCollegeLabel}
                    getCollegeBadgeClass={getCollegeBadgeClass}
                  />

                  <div className="flex justify-end">
                    <button type="button" onClick={handleOpenPdfChat} className="btn-primary flex items-center gap-2">
                      <HiChat className="h-5 w-5" />
                      查看 PDF 與 AI 對話
                    </button>
                  </div>
                </div>
              ) : (
                <div className="card flex h-full min-h-[32rem] flex-col items-center justify-center">
                  <HiChat className="mb-4 h-16 w-16 text-gray-300" />
                  <p className="mb-2 text-gray-600">選擇一筆研究計畫即可查看詳細介紹。</p>
                  <p className="text-sm text-gray-500">接著可進一步開啟 PDF 與 AI 問答模式。</p>
                </div>
              )}
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="relative min-h-0 flex-1 lg:hidden">
            <div className="card flex h-full flex-col overflow-hidden">
              <PdfPanel
                project={selectedProject}
                pdfUrl={selectedProject ? getPdfUrl(selectedProject) : ''}
                onBack={handleBackToOutline}
              />
            </div>

            <div
              className={`absolute inset-y-0 left-0 z-20 w-[min(22rem,calc(100vw-3rem))] transition-transform duration-300 ${
                isMobileChatOpen ? 'translate-x-0' : '-translate-x-[calc(100%-2.75rem)]'
              }`}
            >
              <div className="flex h-full">
                <ChatPanel
                  compact
                  messages={chatMessages}
                  streamingText={streamingText}
                  inputMessage={inputMessage}
                  chatLoading={chatLoading}
                  onInputChange={setInputMessage}
                  onSubmit={handleSendMessage}
                  onCancel={handleCancelStream}
                  onClose={() => setIsMobileChatOpen(false)}
                />

                <div className="flex w-11 items-center justify-center pl-2">
                  <button
                    type="button"
                    onClick={() => setIsMobileChatOpen((prev) => !prev)}
                    className="flex h-28 w-10 flex-col items-center justify-center gap-2 rounded-r-2xl bg-primary-900 px-2 text-white shadow-lg transition hover:bg-primary-800"
                    aria-label={isMobileChatOpen ? '收起 AI 對話框' : '展開 AI 對話框'}
                  >
                    {isMobileChatOpen ? <HiChevronLeft className="h-5 w-5" /> : <HiChevronRight className="h-5 w-5" />}
                    <span className="[writing-mode:vertical-rl] text-xs tracking-[0.2em]">AI 對話</span>
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div className="hidden min-h-0 flex-1 lg:grid lg:grid-cols-2 lg:gap-4">
            <div className="card flex h-full flex-col overflow-hidden">
              <PdfPanel
                project={selectedProject}
                pdfUrl={selectedProject ? getPdfUrl(selectedProject) : ''}
                onBack={handleBackToOutline}
              />
            </div>

            <ChatPanel
              messages={chatMessages}
              streamingText={streamingText}
              inputMessage={inputMessage}
              chatLoading={chatLoading}
              onInputChange={setInputMessage}
              onSubmit={handleSendMessage}
              onCancel={handleCancelStream}
            />
          </div>
        </>
      )}
    </div>
  );
}

function PdfPanel({
  project,
  pdfUrl,
  onBack,
}: {
  project: Project | null;
  pdfUrl: string;
  onBack: () => void;
}) {
  return (
    <>
      <div className="flex flex-shrink-0 items-center gap-3 border-b border-gray-200 px-4 py-2.5">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap text-sm text-primary-600 transition-colors hover:text-primary-800"
        >
          <HiArrowLeft className="h-4 w-4" />
          返回介紹
        </button>
        <span className="shrink-0 text-gray-300">|</span>
        <div className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-gray-700">{project?.title}</span>
        </div>
      </div>
      <div className="flex-1 overflow-hidden">
        {project?.pdfPath ? (
          <PdfViewer pdfUrl={pdfUrl} projectTitle={project.title} hideTitle />
        ) : (
          <div className="flex h-full items-center justify-center">
            <div className="text-center text-gray-500">
              <p className="mb-2 text-lg">目前沒有可顯示的 PDF</p>
              <p className="text-sm">這份研究計畫尚未提供 PDF 檔案。</p>
            </div>
          </div>
        )}
      </div>
    </>
  );
}


function ChatPanel({
  messages,
  streamingText,
  inputMessage,
  chatLoading,
  onInputChange,
  onSubmit,
  onCancel,
  onClose,
  compact = false,
}: {
  messages: ChatMessage[];
  streamingText: string;
  inputMessage: string;
  chatLoading: boolean;
  onInputChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onCancel: () => void;
  onClose?: () => void;
  compact?: boolean;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingText]);

  return (
    <div className="card flex h-full flex-col overflow-hidden">
      <div className="flex flex-shrink-0 items-center justify-between gap-3 border-b border-gray-200 px-4 py-2.5">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-gray-800">AI 對話區</h2>
          <p className="truncate text-xs text-gray-400">可針對研究主題、內容重點與延伸問題進行提問</p>
        </div>
        {onClose ? (
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-gray-200 text-gray-500 transition hover:bg-gray-50"
            aria-label="收起 AI 對話框"
          >
            <HiChevronLeft className="h-5 w-5" />
          </button>
        ) : null}
      </div>

      <div className={`flex-1 space-y-3 overflow-y-auto p-4 ${compact ? 'bg-white' : ''}`}>
        {messages.map((message, index) => (
          <div key={index} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`rounded-lg p-4 ${
                message.role === 'user' ? 'max-w-[80%] bg-primary-700 text-white' : 'max-w-[85%] bg-gray-100 text-gray-900'
              }`}
            >
              {message.role === 'assistant' ? (
                <div className="prose prose-sm prose-gray max-w-none text-sm">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {message.content}
                  </ReactMarkdown>
                </div>
              ) : (
                <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
              )}
            </div>
          </div>
        ))}

        {chatLoading && streamingText ? (
          <div className="flex justify-start">
            <div className="max-w-[85%] rounded-lg bg-gray-100 p-4 text-gray-900">
              <div className="prose prose-sm prose-gray max-w-none text-sm">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {streamingText}
                </ReactMarkdown>
              </div>
              <span className="inline-block h-4 w-0.5 animate-pulse bg-gray-500 align-text-bottom" />
            </div>
          </div>
        ) : chatLoading ? (
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

        <div ref={bottomRef} />
      </div>

      <form onSubmit={onSubmit} className="border-t border-gray-200 p-3">
        <div className="flex gap-2">
          <input
            type="text"
            value={inputMessage}
            onChange={(event) => onInputChange(event.target.value)}
            placeholder="輸入你想了解的研究問題..."
            disabled={chatLoading}
            className="min-w-0 flex-1 rounded-md border border-gray-300 px-4 py-3 transition-colors focus:border-primary-500 focus:ring-2 focus:ring-primary-500 disabled:bg-gray-50 disabled:text-gray-400"
          />
          {chatLoading ? (
            <button
              type="button"
              onClick={onCancel}
              className="btn-secondary shrink-0"
              aria-label="中止回應"
            >
              <HiStop className="h-5 w-5" />
            </button>
          ) : (
            <button type="submit" disabled={!inputMessage.trim()} className="btn-primary shrink-0">
              <HiPaperAirplane className="h-5 w-5" />
            </button>
          )}
        </div>
      </form>
    </div>
  );
}

function ProjectCardContent({
  project,
  getCollegeLabel,
  getCollegeBadgeClass,
}: {
  project: Project;
  getCollegeLabel: (department: string) => string;
  getCollegeBadgeClass: (college: string) => string;
}) {
  return (
    <>
      <div className="mb-2 flex items-start justify-between">
        <span className={`badge text-xs ${getCollegeBadgeClass(getCollegeLabel(project.department))}`}>{getCollegeLabel(project.department)}</span>
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
    </>
  );
}

function ProjectSummary({
  project,
  getCollegeLabel,
  getCollegeBadgeClass,
}: {
  project: Project;
  getCollegeLabel: (department: string) => string;
  getCollegeBadgeClass: (college: string) => string;
}) {
  return (
    <>
      <div className="mb-6">
        <div className="mb-4 flex items-start justify-between">
          <span className={`badge ${getCollegeBadgeClass(getCollegeLabel(project.department))}`}>{getCollegeLabel(project.department)}</span>
          <span className="text-sm text-gray-500">{project.year}</span>
        </div>
        <h2 className="mb-3 text-2xl font-bold text-primary-900">{project.title}</h2>
        <div className="flex items-center gap-4 text-sm text-gray-600">
          <div className="flex items-center">
            <HiUser className="mr-1 h-4 w-4" />
            <span>{project.studentName}</span>
          </div>
          <div className="flex items-center">
            <HiAcademicCap className="mr-1 h-4 w-4" />
            <span>{project.department}</span>
          </div>
        </div>
      </div>

      <div className="mb-8 space-y-6">
        <SectionBlock title="專題摘要">
          這份研究計畫來自 {project.department}，可作為了解研究主題、作品方向與成果呈現方式的參考。
        </SectionBlock>
        <SectionBlock title="閱讀建議">
          建議先查看 PDF 原文掌握研究架構，再透過 AI 問答快速整理重點、釐清術語與延伸討論方向。
        </SectionBlock>
        <SectionBlock title="AI 對話提示">
          你可以直接詢問研究方法、實作內容、成果特色，或請系統幫你整理摘要、列出重點與延伸問題。
        </SectionBlock>
      </div>
    </>
  );
}

function SectionBlock({ title, children }: { title: string; children: ReactNode }) {
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

function createWelcomeMessage(project: Project): ChatMessage {
  return {
    role: 'assistant',
    content: `你現在正在查看「${project.title}」這份研究計畫。如果你想了解研究方向、內容重點或延伸問題，可以直接在這裡提問。`,
  };
}
