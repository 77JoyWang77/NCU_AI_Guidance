import { useState } from 'react';
import { HiChat, HiPlus, HiTrash, HiPaperAirplane, HiX } from 'react-icons/hi';

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

export default function CourseSearchPage() {
  // 模擬對話數據
  const [conversations, setConversations] = useState<Conversation[]>([
    {
      id: '1',
      title: '資工系課程諮詢',
      messages: [
        { role: 'assistant', content: '您好！我是課程諮詢助手。請問有什麼關於課程的問題嗎？', timestamp: new Date() }
      ],
      createdAt: new Date(Date.now() - 86400000 * 2),
      updatedAt: new Date(Date.now() - 86400000 * 2)
    },
    {
      id: '2',
      title: '管理學院選課建議',
      messages: [
        { role: 'assistant', content: '您好！我是課程諮詢助手。請問有什麼關於課程的問題嗎？', timestamp: new Date() },
        { role: 'user', content: '管理學院有哪些熱門課程？', timestamp: new Date() },
        { role: 'assistant', content: '管理學院的熱門課程包括：\n\n1. 企業管理學系：組織行為、策略管理、行銷管理\n2. 財務金融學系：投資學、財務管理、金融市場\n3. 資訊管理學系：資訊系統管理、資料庫系統、數據分析\n\n這些課程都是學生評價較高且對未來就業很有幫助的課程。', timestamp: new Date() }
      ],
      createdAt: new Date(Date.now() - 86400000),
      updatedAt: new Date(Date.now() - 86400000)
    }
  ]);

  const [selectedConversation, setSelectedConversation] = useState<Conversation | null>(null);
  const [inputMessage, setInputMessage] = useState('');
  const [chatLoading, setChatLoading] = useState(false);

  const handleNewConversation = () => {
    const newConv: Conversation = {
      id: Date.now().toString(),
      title: '新對話',
      messages: [
        { role: 'assistant', content: '您好！我是課程諮詢助手。請問有什麼關於課程的問題嗎？', timestamp: new Date() }
      ],
      createdAt: new Date(),
      updatedAt: new Date()
    };
    setConversations([newConv, ...conversations]);
    setSelectedConversation(newConv);
  };

  const handleDeleteConversation = (id: string) => {
    setConversations(conversations.filter(conv => conv.id !== id));
    if (selectedConversation?.id === id) {
      setSelectedConversation(null);
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputMessage.trim() || !selectedConversation) return;

    const userMessage: Message = {
      role: 'user',
      content: inputMessage,
      timestamp: new Date()
    };

    // 更新選中對話
    const updatedConv = {
      ...selectedConversation,
      messages: [...selectedConversation.messages, userMessage],
      updatedAt: new Date(),
      // 如果是第一次用戶提問，更新對話標題
      title: selectedConversation.messages.length === 1 ? inputMessage.slice(0, 20) + '...' : selectedConversation.title
    };

    setSelectedConversation(updatedConv);
    setConversations(conversations.map(conv =>
      conv.id === selectedConversation.id ? updatedConv : conv
    ));
    setInputMessage('');
    setChatLoading(true);

    // 模擬 AI 回應
    setTimeout(() => {
      const aiMessage: Message = {
        role: 'assistant',
        content: generateMockResponse(inputMessage),
        timestamp: new Date()
      };

      const finalConv = {
        ...updatedConv,
        messages: [...updatedConv.messages, aiMessage],
        updatedAt: new Date()
      };

      setSelectedConversation(finalConv);
      setConversations(conversations.map(conv =>
        conv.id === selectedConversation.id ? finalConv : conv
      ));
      setChatLoading(false);
    }, 1500);
  };

  const generateMockResponse = (query: string): string => {
    // 簡單的模擬回應邏輯
    const lowerQuery = query.toLowerCase();

    if (lowerQuery.includes('資工') || lowerQuery.includes('資訊工程')) {
      return '資訊工程學系的核心課程包括：\n\n1. 程式設計（必修）\n2. 資料結構（必修）\n3. 演算法（必修）\n4. 作業系統（必修）\n5. 資料庫系統（選修）\n6. 人工智慧（選修）\n\n這些課程涵蓋了軟體開發的基礎知識，對未來從事軟體工程、AI 開發都很有幫助。';
    }

    if (lowerQuery.includes('學分') || lowerQuery.includes('必修')) {
      return '大部分科系的必修學分約在 60-80 學分之間，選修學分約 40-60 學分。畢業總學分通常需要 128 學分。建議每學期修 15-18 學分，既不會太輕鬆也不會壓力太大。';
    }

    if (lowerQuery.includes('難') || lowerQuery.includes('容易')) {
      return '課程難度因人而異，但一般來說：\n\n- 較容易：通識課程、體育課\n- 中等難度：專業選修、語言課\n- 較困難：微積分、物理、化學等基礎科學必修\n\n建議先從感興趣的領域入手，循序漸進地學習。';
    }

    return '感謝您的提問！這是一個很好的問題。根據課程資料庫，我建議您可以從以下幾個方向來探索：\n\n1. 先確定感興趣的學院或科系\n2. 了解該科系的必修課程\n3. 查看課程的開課時間和授課教師\n4. 參考學長姐的選課經驗\n\n如果您有更具體的問題，歡迎隨時提問！';
  };

  const formatTime = (date: Date) => {
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / 86400000);

    if (days === 0) return '今天';
    if (days === 1) return '昨天';
    if (days < 7) return `${days}天前`;
    return date.toLocaleDateString('zh-TW', { month: 'short', day: 'numeric' });
  };

  return (
    <div className="page-container py-4">
      {/* 緊湊標題列 */}
      <div className="flex items-center justify-between mb-3 py-1">
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-bold text-primary-900">課程諮詢助手</h1>
          <span className="text-sm text-gray-400">·</span>
          <span className="text-sm text-gray-500">透過 AI 助手快速找到你需要的課程資訊</span>
        </div>
        <button
          onClick={handleNewConversation}
          className="btn-primary flex items-center gap-2 py-1.5 px-3 text-sm"
        >
          <HiPlus className="w-4 h-4" />
          新對話
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 左側：對話列表 */}
        <div className="lg:col-span-1">

          {/* 對話列表 */}
          <div className="space-y-3 max-h-[calc(100vh-320px)] overflow-y-auto">
            {conversations.length === 0 ? (
              <div className="card p-8 text-center text-gray-500">
                <p>還沒有對話</p>
                <p className="text-sm mt-2">點擊上方按鈕開始新對話</p>
              </div>
            ) : (
              conversations.map((conv) => (
                <div
                  key={conv.id}
                  className={`card-interactive p-4 cursor-pointer relative group ${
                    selectedConversation?.id === conv.id
                      ? 'ring-2 ring-primary-600'
                      : ''
                  }`}
                  onClick={() => setSelectedConversation(conv)}
                >
                  <div className="flex items-start justify-between mb-2">
                    <HiChat className="w-5 h-5 text-primary-600 flex-shrink-0 mt-0.5" />
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteConversation(conv.id);
                      }}
                      className="opacity-0 group-hover:opacity-100 text-red-500 hover:text-red-700 transition-opacity"
                    >
                      <HiTrash className="w-4 h-4" />
                    </button>
                  </div>
                  <h3 className="text-sm font-semibold text-primary-900 mb-1 line-clamp-2">
                    {conv.title}
                  </h3>
                  <div className="text-xs text-gray-500">
                    {formatTime(conv.updatedAt)}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* 右側：對話內容 */}
        <div className="lg:col-span-2">
          {selectedConversation ? (
            <div className="card h-[calc(100vh-240px)] flex flex-col">
              {/* 對話標題 */}
              <div className="px-6 py-4 border-b border-gray-200 flex-shrink-0">
                <h2 className="text-lg font-semibold text-gray-800">{selectedConversation.title}</h2>
                <p className="text-sm text-gray-500 mt-1">根據課程資料庫提供建議</p>
              </div>

              {/* 對話消息 */}
              <div className="flex-1 overflow-y-auto p-6 space-y-4">
                {selectedConversation.messages.map((msg, index) => (
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
                      <p className="text-sm leading-relaxed whitespace-pre-line">{msg.content}</p>
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

              {/* 輸入框 */}
              <form onSubmit={handleSendMessage} className="p-6 border-t border-gray-200">
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
          ) : (
            <div className="card h-[calc(100vh-240px)] flex flex-col items-center justify-center">
              <HiChat className="w-16 h-16 text-gray-300 mb-4" />
              <p className="text-gray-600 mb-2">選擇一個對話或開始新對話</p>
              <p className="text-sm text-gray-500">AI 助手會根據課程資料庫回答你的問題</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
