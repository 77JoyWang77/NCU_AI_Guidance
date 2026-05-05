import { apiClient } from './client';
import { getFirebaseIdToken } from '../auth/firebase';
import type {
  AssessmentMode,
  Question,
  Answer,
  AssessmentResult,
  Course,
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
};
