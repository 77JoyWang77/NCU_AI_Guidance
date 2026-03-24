import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import { useEffect } from 'react';
import Layout from './components/Layout';
import HomePage from './pages/HomePage';
import AssessmentPage from './pages/AssessmentPage';
import ProjectsPage from './pages/ProjectsPage';
import CoursesPage from './pages/CoursesPage';
import CourseSearchPage from './pages/CourseSearchPage';

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => { window.scrollTo(0, 0); }, [pathname]);
  return null;
}

function App() {
  return (
    <Router>
      <ScrollToTop />
      <Layout>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/assessment" element={<AssessmentPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/courses" element={<CoursesPage />} />
          <Route path="/course-search" element={<CourseSearchPage />} />
        </Routes>
      </Layout>
    </Router>
  );
}

export default App;
