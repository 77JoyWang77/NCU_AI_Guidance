import { apiClient } from './client';
import { getFirebaseIdToken } from '../auth/firebase';
import type {
  AssessmentMode,
  Question,
  Answer,
  AssessmentResult,
  Course,
  CourseAskResponse,
  CourseSemanticSearchParams,
  CourseSemanticSearchResponse,
  Project,
  ChatApiResponse,
  StreamEvent,
} from '../types';

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000/api';

export const authAPI = {
  me: async (): Promise<{
    id: string;
    email: string;
    name: string;
    picture: string;
  }> => {
    const response = await apiClient.get('/auth/me');
    return response.data;
  },
};

// 科系兴趣量表 API
export const assessmentAPI = {
  getQuestions: async (mode: AssessmentMode): Promise<Question[]> => {
    const response = await apiClient.get(`/assessment/questions?mode=${mode}`);
    return response.data;
  },

  submitAnswers: async (mode: AssessmentMode, answers: Answer[]): Promise<AssessmentResult> => {
    const response = await apiClient.post('/assessment/submit', { mode, answers });
    return response.data;
  },

  filterBySubjects: async (subjects: string[]): Promise<{ departments: string[] }> => {
    const response = await apiClient.post('/assessment/filter-by-subjects', { subjects });
    return response.data;
  },
};

// 课程 API
export const courseAPI = {
  getCourses: async (filters?: {
    college?: string;
    department?: string;
    type?: string; // 必修/选修
  }): Promise<Course[]> => {
    const response = await apiClient.get('/courses', { params: filters });
    return response.data;
  },

  getCourseById: async (id: string): Promise<Course> => {
    const response = await apiClient.get(`/courses/${id}`);
    return response.data;
  },

  searchCourses: async (query: string): Promise<Course[]> => {
    const response = await apiClient.post('/course-search', { query });
    return response.data;
  },

  semanticSearch: async (params: CourseSemanticSearchParams): Promise<CourseSemanticSearchResponse> => {
    const response = await apiClient.post('/courses/semantic-search', params);
    return response.data;
  },

  askCourse: async (courseId: string, question: string): Promise<CourseAskResponse> => {
    const response = await apiClient.post(`/courses/${encodeURIComponent(courseId)}/ask`, { question });
    return response.data;
  },
};

// 聊天 API
export const chatAPI = {
  send: async (
    question: string,
    session_id?: string,
    college?: string,
    dept?: string,
  ): Promise<ChatApiResponse> => {
    const response = await apiClient.post('/chat', {
      question, session_id, college, dept,
    });
    return response.data;
  },
  clearSession: async (session_id: string): Promise<void> => {
    await apiClient.delete(`/chat/session/${session_id}`);
  },
  getSessions: async (): Promise<Array<{
    session_id: string;
    title: string;
    updated_at: string;
    turn_count: number;
  }>> => {
    const response = await apiClient.get('/chat/sessions');
    return response.data;
  },
  getSession: async (session_id: string): Promise<{
    session_id: string;
    title: string;
    updated_at: string;
    turns: Array<{
      user: string;
      assistant: string;
      course_cards: import('../types').CourseCard[];
      tools_used: string[];
      created_at: string;
    }>;
  }> => {
    const response = await apiClient.get(`/chat/session/${session_id}`);
    return response.data;
  },
};

// 串流聊天 API
export const chatStreamAPI = {
  stream(
    question: string,
    handlers: {
      onToken:       (text: string) => void;
      onToolStart:   (tool: string, args: Record<string, unknown>) => void;
      onToolDone:    (tool: string, count?: number, coursesFound?: string[], scores?: number[], scoreType?: string) => void;
      onVerifyStart: (poolSize: number) => void;
      onVerifyDone:  (selected: string[], filteredOut: string[], method?: 'tag' | 'llm') => void;
      onDone:        (event: StreamEvent) => void;
      onError:       (msg: string) => void;
    },
    session_id?: string,
    college?: string,
    dept?: string,
  ): AbortController {
    const controller = new AbortController();

    getFirebaseIdToken()
      .then((token) => fetch(`${API_BASE}/chat/stream`, {
      method:  'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body:    JSON.stringify({ question, session_id, college, dept }),
      signal:  controller.signal,
      }))
      .then(async (res) => {
        if (!res.ok) { handlers.onError(`HTTP ${res.status}`); return; }
        const reader = res.body!.getReader();
        const decoder = new TextDecoder();
        let buf = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split('\n');
          buf = lines.pop() ?? '';
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const ev: StreamEvent = JSON.parse(line.slice(6));
              if (ev.type === 'token')           handlers.onToken(ev.text ?? '');
              else if (ev.type === 'tool_start') handlers.onToolStart(ev.tool ?? '', ev.args ?? {});
              else if (ev.type === 'tool_done')  handlers.onToolDone(ev.tool ?? '', ev.count, ev.courses_found, ev.scores, ev.score_type);
              else if (ev.type === 'verify_start') handlers.onVerifyStart(ev.pool_size ?? 0);
              else if (ev.type === 'verify_done')  handlers.onVerifyDone(ev.selected ?? [], ev.filtered_out ?? [], ev.method);
              else if (ev.type === 'done')       handlers.onDone(ev);
              else if (ev.type === 'error')      handlers.onError(ev.message ?? '未知錯誤');
            } catch { /* malformed chunk */ }
          }
        }
      })
      .catch((err: Error) => {
        if (err.name !== 'AbortError') handlers.onError(err.message);
      });

    return controller;
  },
};

// 學習傾向分析 API
export interface AnalyticsOverview {
  total_sessions: number;
  total_turns: number;
  total_courses_explored: number;
  fav_college: string;
}

export interface AnalyticsDistItem {
  name: string;
  count: number;
  pct: number;
}

export interface AnalyticsToolItem {
  tool: string;
  label: string;
  count: number;
}

export interface AnalyticsCourseItem {
  name: string;
  count: number;
}

export interface AnalyticsData {
  overview: AnalyticsOverview;
  dept_distribution: AnalyticsDistItem[];
  college_distribution: AnalyticsDistItem[];
  tool_usage: AnalyticsToolItem[];
  top_courses: AnalyticsCourseItem[];
  top_domain_tags: { tag: string; count: number }[];
}

export const analyticsAPI = {
  get: async (): Promise<AnalyticsData> => {
    const response = await apiClient.get('/chat/analytics');
    return response.data;
  },
};

// 大专生计划 API
export const projectAPI = {
  getProjects: async (filters?: {
    department?: string;
    year?: string;
  }): Promise<Project[]> => {
    const response = await apiClient.get('/projects', { params: filters });
    return response.data;
  },

  getProjectById: async (id: string): Promise<Project> => {
    const response = await apiClient.get(`/projects/${id}`);
    return response.data;
  },

  chatWithProject: async (projectId: string, message: string): Promise<string> => {
    const response = await apiClient.post(`/projects/${projectId}/chat`, { message });
    return response.data.reply;
  },

  streamChat(
    projectId: string,
    message: string,
    handlers: {
      onToken: (text: string) => void;
      onDone: (sessionId: string, cancelled?: boolean, sources?: string[]) => void;
      onError: (msg: string) => void;
      onReplace?: (text: string) => void;
      onSessionId?: (sessionId: string) => void;
    },
    threadId?: string,
  ): AbortController {
    const controller = new AbortController();

    getFirebaseIdToken()
      .then((token) =>
        fetch(`${API_BASE}/projects/${projectId}/chat/stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ message, thread_id: threadId ?? null }),
          signal: controller.signal,
        }),
      )
      .then(async (res) => {
        if (!res.ok) { handlers.onError(`HTTP ${res.status}`); return; }
        const reader = res.body!.getReader();
        const decoder = new TextDecoder();
        let buf = '';

        let parseErrorStreak = 0;
        const processLine = (line: string) => {
          if (!line.startsWith('data: ')) return;
          try {
            const ev = JSON.parse(line.slice(6)) as {
              token?: string;
              done?: boolean;
              session_id?: string;
              cancelled?: boolean;
              heartbeat?: boolean;
              error?: string;
              replace?: string;
              sources?: string[];
            };
            parseErrorStreak = 0;
            if (ev.heartbeat) return;
            if (ev.error) { handlers.onError(ev.error); return; }
            if (ev.replace !== undefined) { handlers.onReplace?.(ev.replace); return; }
            // session_id-only event (no token/done): front-load the session id so cancel works from turn 1.
            if (ev.session_id && !ev.done && ev.token === undefined) { handlers.onSessionId?.(ev.session_id); return; }
            if (ev.token !== undefined) handlers.onToken(ev.token);
            if (ev.done) handlers.onDone(ev.session_id ?? '', ev.cancelled, ev.sources ?? []);
          } catch (e) {
            console.error('[SSE] parse error on line:', line.slice(6, 120), e);
            parseErrorStreak += 1;
            if (parseErrorStreak >= 3) {
              handlers.onError('串流格式異常，請重新整理後再試。');
            }
          }
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            buf += decoder.decode(); // flush multi-byte sequences
            break;
          }
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split('\n');
          buf = lines.pop() ?? '';
          for (const line of lines) processLine(line);
        }
        // flush any remaining data not ending with \n
        for (const line of buf.split('\n')) processLine(line);
      })
      .catch((err: Error) => {
        if (err.name !== 'AbortError') handlers.onError(err.message);
      });

    return controller;
  },

  cancelChat: async (projectId: string, threadId: string): Promise<void> => {
    await apiClient.post(`/projects/${projectId}/chat/${threadId}/cancel`);
  },
};
