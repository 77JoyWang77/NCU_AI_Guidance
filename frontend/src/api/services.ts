import { apiClient } from './client';
import type {
  AssessmentMode,
  Question,
  Answer,
  AssessmentResult,
  Course,
  Project
} from '../types';

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
