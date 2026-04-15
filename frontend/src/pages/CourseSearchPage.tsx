import { useMemo, useState } from 'react';
import {
  HiChat,
  HiChevronLeft,
  HiChevronRight,
  HiMenu,
  HiPaperAirplane,
  HiPlus,
  HiTrash,
} from 'react-icons/hi';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
}

const assistantGreeting = '你好，我是課程搜尋助理。你可以直接問我課程方向、學分安排，或想比較的學院特色。';

export default function CourseSearchPage() {
  const [conversations, setConversations] = useState<Conversation[]>([
    {
      id: '1',
      title: '資訊工程課程方向',
      messages: [{ role: 'assistant', content: assistantGreeting, timestamp: new Date() }],
      createdAt: new Date(Date.now() - 86400000 * 2),
      updatedAt: new Date(Date.now() - 86400000 * 2),
    },
    {
      id: '2',
      title: '管理學院選課建議',
      messages: [
        { role: 'assistant', content: assistantGreeting, timestamp: new Date(Date.now() - 86400000) },
        { role: 'user', content: '管理學院有哪些適合新生先了解的課程？', timestamp: new Date(Date.now() - 86400000) },
        {
          role: 'assistant',
          content:
            '如果你剛開始接觸管理學院，可以先從三個方向認識：\n\n1. 經濟學系，適合想理解市場分析與理論的人。\n2. 企業管理學系，會接觸組織、行銷與策略。\n3. 資訊管理學系，結合管理與資訊工具，實作面較高。\n\n如果你願意，我也可以再依照「偏商管」或「偏資料分析」幫你縮小範圍。',
          timestamp: new Date(Date.now() - 86400000),
        },
      ],
      createdAt: new Date(Date.now() - 86400000),
      updatedAt: new Date(Date.now() - 86400000),
    },
  ]);
  const [selectedConversationId, setSelectedConversationId] = useState<string>('1');
  const [inputMessage, setInputMessage] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  const selectedConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === selectedConversationId) ?? null,
    [conversations, selectedConversationId]
  );

  const handleNewConversation = () => {
    const newConversation: Conversation = {
      id: Date.now().toString(),
      title: '新對話',
      messages: [{ role: 'assistant', content: assistantGreeting, timestamp: new Date() }],
      createdAt: new Date(),
      updatedAt: new Date(),
    };

    setConversations((prev) => [newConversation, ...prev]);
    setSelectedConversationId(newConversation.id);
    setInputMessage('');
  };

  const handleDeleteConversation = (id: string) => {
    const nextConversations = conversations.filter((conversation) => conversation.id !== id);
    setConversations(nextConversations);
    if (selectedConversationId === id) {
      setSelectedConversationId(nextConversations[0]?.id ?? '');
      setInputMessage('');
    }
  };

  const handleSendMessage = (event: React.FormEvent) => {
    event.preventDefault();
    if (!inputMessage.trim() || !selectedConversation) return;

    const messageText = inputMessage.trim();
    const userMessage: Message = {
      role: 'user',
      content: messageText,
      timestamp: new Date(),
    };

    const updatedConversation: Conversation = {
      ...selectedConversation,
      messages: [...selectedConversation.messages, userMessage],
      updatedAt: new Date(),
      title: selectedConversation.messages.length === 1 ? `${messageText.slice(0, 18)}...` : selectedConversation.title,
    };

    setConversations((prev) =>
      prev.map((conversation) => (conversation.id === selectedConversation.id ? updatedConversation : conversation))
    );
    setInputMessage('');
    setChatLoading(true);

    window.setTimeout(() => {
      const assistantMessage: Message = {
        role: 'assistant',
        content: generateMockResponse(messageText),
        timestamp: new Date(),
      };

      setConversations((prev) =>
        prev.map((conversation) =>
          conversation.id === selectedConversation.id
            ? {
                ...conversation,
                messages: [...updatedConversation.messages, assistantMessage],
                updatedAt: new Date(),
              }
            : conversation
        )
      );
      setChatLoading(false);
    }, 1000);
  };

  const generateMockResponse = (query: string): string => {
    const lowerQuery = query.toLowerCase();

    if (lowerQuery.includes('資工') || lowerQuery.includes('資訊工程')) {
      return '資訊工程可以先從三塊理解：\n\n1. 程式設計與資料結構。\n2. 演算法、系統與計算機基礎。\n3. AI、資料科學與網路應用。\n\n如果你想，我可以再幫你分成「新手先看」和「進階延伸」兩組。';
    }

    if (lowerQuery.includes('學分') || lowerQuery.includes('必修')) {
      return '建議先區分必修、選修和通識來源，再看單學期學分是否平均。對大一學生來說，先用核心必修搭配 1 到 2 門探索型選修，通常會比較穩。';
    }

    if (lowerQuery.includes('管理') || lowerQuery.includes('商管')) {
      return '管理學院可以先看三個方向：\n\n- 經濟偏分析與理論。\n- 企管偏組織、行銷與策略。\n- 資管偏系統、資料與管理整合。\n\n如果你願意，我可以再用「偏商業」或「偏資料」幫你縮小。';
    }

    return '我可以協助你從課程名稱、學分配置、學院特色和學習方向來整理課程線索。\n\n你可以試著問我：\n1. 某個學系大一適合先看哪些課。\n2. 想走 AI 或資料分析可以注意哪些課程。\n3. 某個學院的必修與選修差別。\n4. 如何依興趣篩選課程方向。';
  };

  const formatTime = (date: Date) => {
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / 86400000);

    if (days === 0) return '今天';
    if (days === 1) return '昨天';
    if (days < 7) return `${days} 天前`;
    return date.toLocaleDateString('zh-TW', { month: 'short', day: 'numeric' });
  };

  return (
    <div className="page-container flex h-full flex-col py-3">
      <div className="mb-3 flex flex-shrink-0 items-center justify-between">
        <div className="flex items-center gap-2">
          <h1 className="text-base font-bold text-primary-900">課程搜尋</h1>
          <span className="text-sm text-gray-400">/</span>
          <span className="text-sm text-gray-500">用 AI 對話方式快速整理課程方向與學習線索</span>
        </div>
        <button onClick={handleNewConversation} className="btn-primary flex items-center gap-2 px-3 py-1.5 text-sm">
          <HiPlus className="h-4 w-4" />
          新對話
        </button>
      </div>

      <div className="flex min-h-0 flex-1 gap-4">
        <aside
          className={`card hidden min-h-0 flex-shrink-0 overflow-hidden transition-all duration-300 lg:flex ${
            isSidebarCollapsed ? 'w-[88px]' : 'w-[320px]'
          }`}
        >
          <div className="flex w-full flex-col">
            <div className={`border-b border-gray-200 p-3 ${isSidebarCollapsed ? 'flex flex-col items-center gap-3' : 'flex items-center justify-between gap-2'}`}>
              {isSidebarCollapsed ? (
                <>
                  <button
                    type="button"
                    onClick={() => setIsSidebarCollapsed(false)}
                    className="rounded-xl p-2 text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
                    aria-label="展開側欄"
                  >
                    <HiChevronRight className="h-5 w-5" />
                  </button>
                  <button
                    type="button"
                    onClick={handleNewConversation}
                    className="rounded-xl bg-primary-900 p-2 text-white transition hover:bg-primary-800"
                    aria-label="新增對話"
                  >
                    <HiPlus className="h-5 w-5" />
                  </button>
                </>
              ) : (
                <>
                  <div className="flex items-center gap-2">
                    <HiMenu className="h-5 w-5 text-primary-700" />
                    <span className="text-sm font-semibold text-slate-800">對話紀錄</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setIsSidebarCollapsed(true)}
                    className="rounded-xl p-2 text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
                    aria-label="收合側欄"
                  >
                    <HiChevronLeft className="h-5 w-5" />
                  </button>
                </>
              )}
            </div>

            <div className="flex-1 space-y-2 overflow-y-auto p-3">
              {conversations.map((conversation) => (
                <button
                  key={conversation.id}
                  type="button"
                  onClick={() => setSelectedConversationId(conversation.id)}
                  className={`w-full rounded-2xl border p-3 text-left transition ${
                    selectedConversationId === conversation.id
                      ? 'border-primary-300 bg-primary-50'
                      : 'border-transparent bg-white hover:border-slate-200 hover:bg-slate-50'
                  } ${isSidebarCollapsed ? 'flex justify-center' : ''}`}
                >
                  {isSidebarCollapsed ? (
                    <HiChat className="h-5 w-5 text-primary-700" />
                  ) : (
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <HiChat className="h-4 w-4 flex-shrink-0 text-primary-700" />
                        </div>
                        <h3 className="mt-2 line-clamp-2 text-sm font-semibold text-slate-900">{conversation.title}</h3>
                        <p className="mt-2 text-xs text-slate-500">{formatTime(conversation.updatedAt)}</p>
                      </div>
                      <button
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          handleDeleteConversation(conversation.id);
                        }}
                        className="rounded-lg p-1 text-rose-500 transition hover:bg-rose-50 hover:text-rose-700"
                        aria-label="刪除對話"
                      >
                        <HiTrash className="h-4 w-4" />
                      </button>
                    </div>
                  )}
                </button>
              ))}
            </div>
          </div>
        </aside>

        <div className="flex min-h-0 flex-1 flex-col">
          {selectedConversation ? (
            <div className="card flex h-full flex-col">
              <div className="flex flex-shrink-0 items-center justify-between gap-3 border-b border-gray-200 px-4 py-3">
                <div className="flex min-w-0 items-center gap-3">
                  <button
                    type="button"
                    onClick={() => setIsSidebarCollapsed((prev) => !prev)}
                    className="hidden rounded-xl p-2 text-slate-600 transition hover:bg-slate-100 hover:text-slate-900 lg:inline-flex"
                    aria-label="切換側欄"
                  >
                    {isSidebarCollapsed ? <HiChevronRight className="h-5 w-5" /> : <HiChevronLeft className="h-5 w-5" />}
                  </button>
                  <div className="min-w-0">
                    <h2 className="truncate text-sm font-semibold text-gray-800">{selectedConversation.title}</h2>
                    <span className="text-xs text-gray-400">可以持續追問課程方向、學分配置與學院特色</span>
                  </div>
                </div>
              </div>

              <div className="flex-1 space-y-3 overflow-y-auto p-4">
                {selectedConversation.messages.map((message, index) => (
                  <div key={index} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div
                      className={`max-w-[82%] rounded-2xl p-4 ${
                        message.role === 'user' ? 'bg-primary-700 text-white' : 'bg-gray-100 text-gray-900'
                      }`}
                    >
                      <p className="whitespace-pre-line text-sm leading-relaxed">{message.content}</p>
                    </div>
                  </div>
                ))}

                {chatLoading ? (
                  <div className="flex justify-start">
                    <div className="rounded-2xl bg-gray-100 p-4 text-gray-900">
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
                    disabled={chatLoading}
                    placeholder="輸入你想查詢的課程、學院或學習方向"
                    className="flex-1 rounded-xl border border-gray-300 px-4 py-3 transition-colors focus:border-primary-500 focus:ring-2 focus:ring-primary-500 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
                  />
                  <button
                    type="submit"
                    disabled={chatLoading || !inputMessage.trim()}
                    className="btn-primary disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <HiPaperAirplane className="h-5 w-5" />
                  </button>
                </div>
              </form>
            </div>
          ) : (
            <div className="card flex h-full flex-col items-center justify-center">
              <HiChat className="mb-4 h-16 w-16 text-gray-300" />
              <p className="mb-2 text-gray-600">請先選擇一個對話，或建立新的對話。</p>
              <p className="text-sm text-gray-500">你可以用自然語言詢問課程方向、學分安排或學院特色。</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
