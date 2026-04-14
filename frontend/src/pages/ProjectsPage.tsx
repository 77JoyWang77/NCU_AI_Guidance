import { useState, useEffect, useMemo } from 'react';
import { projectAPI } from '../api/services';
import type { Project } from '../types';
import { HiAcademicCap, HiUser, HiChat, HiPaperAirplane, HiArrowLeft } from 'react-icons/hi';
import PdfViewer from '../components/PdfViewer';

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [viewMode, setViewMode] = useState<'outline' | 'pdf-chat'>('outline'); // 新增：視圖模式
  const [chatMessages, setChatMessages] = useState<Array<{role: 'user' | 'assistant'; content: string}>>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [filterYear, setFilterYear] = useState('');
  const [filterDept, setFilterDept] = useState('');

  const years = useMemo(() =>
    [...new Set(projects.map(p => p.year))].sort((a, b) => b.localeCompare(a)),
    [projects]
  );

  const departments = useMemo(() =>
    [...new Set(projects.map(p => p.department))].sort(),
    [projects]
  );

  const filteredProjects = useMemo(() =>
    projects.filter(p =>
      (!filterYear || p.year === filterYear) &&
      (!filterDept || p.department === filterDept)
    ),
    [projects, filterYear, filterDept]
  );

  useEffect(() => {
    loadProjects();
  }, []);

  const loadProjects = async () => {
    try {
      const data = await projectAPI.getProjects();
      setProjects(data);
    } catch (error) {
      console.error('載入計畫失敗:', error);
    }
  };

  const handleSelectProject = (project: Project) => {
    setSelectedProject(project);
    setChatMessages([
      { role: 'assistant', content: `您好！我是「${project.title}」研究計畫的助手。請問有什麼問題嗎？` }
    ]);
  };

  const handleEnterPdfChat = () => {
    setViewMode('pdf-chat');
  };

  const handleBackToOutline = () => {
    setViewMode('outline');
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputMessage.trim() || !selectedProject) return;

    const userMessage = inputMessage;
    setChatMessages([...chatMessages, { role: 'user', content: userMessage }]);
    setInputMessage('');
    setChatLoading(true);

    try {
      const reply = await projectAPI.chatWithProject(selectedProject.id, userMessage);
      setChatMessages(prev => [...prev, { role: 'assistant', content: reply }]);
    } catch (error) {
      console.error('發送訊息失敗:', error);
      setChatMessages(prev => [...prev, { role: 'assistant', content: '抱歉，發生錯誤了。請稍後再試。' }]);
    } finally {
      setChatLoading(false);
    }
  };

  const getTypeLabel = (type: string) => {
    switch(type) {
      case 'E': return '工程';
      case 'H': return '人文';
      case 'M': return '數理';
      case 'B': return '生物';
      default: return type;
    }
  };

  const getTypeBadgeClass = (type: string) => {
    switch(type) {
      case 'E': return 'bg-blue-100 text-blue-800';
      case 'H': return 'bg-purple-100 text-purple-800';
      case 'M': return 'bg-green-100 text-green-800';
      case 'B': return 'bg-amber-100 text-amber-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const getPdfUrl = (project: Project): string => {
    if (!project.pdfPath) return '';
    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const baseUrl = apiUrl.replace('/api', '');
    // pdfPath 格式：科系名\文件名.pdf
    // 需要轉換為 URL 編碼
    const encodedPath = project.pdfPath.split('\\').map(encodeURIComponent).join('/');
    return `${baseUrl}/pdfs/${encodedPath}`;
  };

  return (
    <div className="h-full flex flex-col page-container py-3">
      {/* 緊湊標題列 - 進入完整報告後隱藏 */}
      {viewMode !== 'pdf-chat' && (
        <div className="flex items-center justify-between mb-3 flex-shrink-0">
          <div className="flex items-center gap-2">
            <h1 className="text-base font-bold text-primary-900">大專生研究計畫</h1>
            <span className="text-sm text-gray-400">·</span>
            <span className="text-sm text-gray-500">探索學長姐的研究成果，了解科系實際研究方向</span>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={filterYear}
              onChange={(e) => setFilterYear(e.target.value)}
              className="px-2 py-1.5 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="">全部年分</option>
              {years.map(y => <option key={y} value={y}>{y} 學年</option>)}
            </select>
            <select
              value={filterDept}
              onChange={(e) => setFilterDept(e.target.value)}
              className="px-2 py-1.5 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 max-w-[160px]"
            >
              <option value="">全部科系</option>
              {departments.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
            <span className="text-sm text-gray-500 shrink-0">
              共 <span className="text-primary-700 font-semibold">{filteredProjects.length}</span> 個
            </span>
          </div>
        </div>
      )}

      {viewMode === 'outline' ? (
        // 大綱視圖（左側列表 + 右側大綱）
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 flex-1 min-h-0">
        {/* 左側：計畫列表 */}
        <div className="lg:col-span-1 flex flex-col min-h-0">

              <div className="space-y-2 overflow-y-auto flex-1">
                {filteredProjects.map((project) => (
                  <div
                    key={project.id}
                    className={`card-interactive p-4 cursor-pointer ${
                      selectedProject?.id === project.id
                        ? 'ring-2 ring-primary-600'
                        : ''
                    }`}
                    onClick={() => handleSelectProject(project)}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <span className={`badge text-xs ${getTypeBadgeClass(project.type)}`}>
                        {getTypeLabel(project.type)}
                      </span>
                      <span className="text-xs text-gray-500">{project.year} 學年</span>
                    </div>

                    <h3 className="text-sm font-semibold text-primary-900 mb-2 line-clamp-2 leading-tight">
                      {project.title}
                    </h3>
                    <div className="space-y-1 text-xs text-gray-600">
                      <div className="flex items-center">
                        <HiUser className="w-3 h-3 mr-1" />
                        <span>{project.studentName}</span>
                      </div>
                      <div className="flex items-center">
                        <HiAcademicCap className="w-3 h-3 mr-1" />
                        <span className="line-clamp-1">{project.department}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

        {/* 右側：研究大綱或提示 */}
        <div className="lg:col-span-2 min-h-0 overflow-y-auto">
          {selectedProject ? (
            <div className="card p-8 relative">
                <div className="mb-6">
                  <div className="flex items-start justify-between mb-4">
                    <span className={`badge ${getTypeBadgeClass(selectedProject.type)}`}>
                      {getTypeLabel(selectedProject.type)}
                    </span>
                    <span className="text-sm text-gray-500">{selectedProject.year} 學年</span>
                  </div>
                  <h2 className="text-2xl font-bold text-primary-900 mb-3">{selectedProject.title}</h2>
                  <div className="flex items-center gap-4 text-sm text-gray-600">
                    <div className="flex items-center">
                      <HiUser className="w-4 h-4 mr-1" />
                      <span>{selectedProject.studentName}</span>
                    </div>
                    <div className="flex items-center">
                      <HiAcademicCap className="w-4 h-4 mr-1" />
                      <span>{selectedProject.department}</span>
                    </div>
                  </div>
                </div>

                {/* 研究大綱內容 */}
                <div className="space-y-6 mb-8">
                  <div>
                    <h3 className="text-lg font-semibold text-primary-900 mb-3 flex items-center">
                      <span className="w-1 h-6 bg-primary-600 mr-3"></span>
                      研究動機與問題
                    </h3>
                    <p className="text-gray-700 leading-relaxed pl-4">
                      本研究旨在探討{selectedProject.department}領域中的核心議題，透過系統性的研究方法，
                      深入分析相關現象與問題。研究動機源於對該領域實際應用與理論發展的關注，
                      期望能為學術界與實務界提供有價值的見解與貢獻。
                    </p>
                  </div>

                  <div>
                    <h3 className="text-lg font-semibold text-primary-900 mb-3 flex items-center">
                      <span className="w-1 h-6 bg-primary-600 mr-3"></span>
                      研究方法
                    </h3>
                    <p className="text-gray-700 leading-relaxed pl-4">
                      採用質性與量化並重的研究方法，包括文獻回顧、實驗設計、資料收集與分析等步驟。
                      透過嚴謹的研究設計與執行，確保研究結果的可信度與有效性。
                      研究過程中將運用多種研究工具與技術，以全面性地探討研究問題。
                    </p>
                  </div>

                  <div>
                    <h3 className="text-lg font-semibold text-primary-900 mb-3 flex items-center">
                      <span className="w-1 h-6 bg-primary-600 mr-3"></span>
                      研究結果
                    </h3>
                    <p className="text-gray-700 leading-relaxed pl-4">
                      研究成果顯示在{selectedProject.department}領域中具有重要的理論與實務意義。
                      透過深入的分析與討論，本研究提出了創新的見解與建議，
                      對於未來相關研究方向與實務應用具有重要的參考價值。
                    </p>
                  </div>
                </div>

              {/* 進入 PDF 與對話按鈕 */}
              <div className="flex justify-end">
                <button
                  onClick={handleEnterPdfChat}
                  className="btn-primary flex items-center gap-2"
                >
                  <HiChat className="w-5 h-5" />
                  查看完整報告與AI對話
                </button>
              </div>
            </div>
          ) : (
            <div className="card h-full flex flex-col items-center justify-center">
              <HiChat className="w-16 h-16 text-gray-300 mb-4" />
              <p className="text-gray-600 mb-2">選擇一個計畫查看大綱</p>
              <p className="text-sm text-gray-500">點擊左側的計畫卡片</p>
            </div>
          )}
        </div>
      </div>
      ) : viewMode === 'pdf-chat' && selectedProject ? (
        // PDF + 對話視圖（全高，不帶外部間距）
        <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* PDF Viewer */}
            <div className="card overflow-hidden flex flex-col h-full">
              {/* PDF 面板 header：含返回按鈕 */}
              <div className="px-4 py-2.5 border-b border-gray-200 flex-shrink-0 flex items-center gap-2">
                <button
                  onClick={handleBackToOutline}
                  className="flex items-center gap-1 text-sm text-primary-600 hover:text-primary-800 transition-colors"
                >
                  <HiArrowLeft className="w-4 h-4" />
                  返回大綱
                </button>
                <span className="text-gray-300">|</span>
                <span className="text-sm font-medium text-gray-700 truncate">{selectedProject.title}</span>
              </div>
              <div className="flex-1 overflow-hidden">
              {selectedProject.pdfPath ? (
                <PdfViewer
                  pdfUrl={getPdfUrl(selectedProject)}
                  projectTitle={selectedProject.title}
                  hideTitle
                />
              ) : (
                <div className="h-full flex items-center justify-center">
                  <div className="text-center text-gray-500">
                    <p className="text-lg mb-2">PDF 文件不可用</p>
                    <p className="text-sm">此計畫暫無 PDF 文檔</p>
                  </div>
                </div>
              )}
              </div>
            </div>

            {/* Chat Area */}
            <div className="card h-full flex flex-col">
              {/* Chat Header - 緊湊版 */}
              <div className="px-4 py-2.5 border-b border-gray-200 flex-shrink-0 flex items-center gap-2">
                <h2 className="text-sm font-semibold text-gray-800">AI 問答助手</h2>
                <span className="text-xs text-gray-400">· 提問關於這份研究計畫的任何問題</span>
              </div>

            {/* Chat Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {chatMessages.map((msg, index) => (
                <div
                  key={index}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[80%] p-4 rounded-lg ${
                      msg.role === 'user'
                        ? 'bg-primary-700 text-white'
                        : 'bg-gray-100 text-gray-900'
                    }`}
                  >
                    <p className="text-sm leading-relaxed">{msg.content}</p>
                  </div>
                </div>
              ))}
              {chatLoading && (
                <div className="flex justify-start">
                  <div className="bg-gray-100 text-gray-900 p-4 rounded-lg">
                    <div className="flex space-x-2">
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100"></div>
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200"></div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Input */}
            <form onSubmit={handleSendMessage} className="p-3 border-t border-gray-200">
              <div className="flex gap-3">
                <input
                  type="text"
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  placeholder="輸入你的問題..."
                  className="flex-1 px-4 py-3 border border-gray-300 rounded-md focus:ring-2 focus:ring-primary-500 focus:border-primary-500 transition-colors"
                />
                <button
                  type="submit"
                  disabled={chatLoading || !inputMessage.trim()}
                  className="btn-primary"
                >
                  <HiPaperAirplane className="w-5 h-5" />
                </button>
              </div>
            </form>
            </div>
          </div>
      ) : null}
    </div>
  );
}
