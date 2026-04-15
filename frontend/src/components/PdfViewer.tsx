import React, { useState } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import { FiZoomIn, FiZoomOut, FiRotateCw } from 'react-icons/fi';
import '../styles/pdf-viewer.css';

// 設置 PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

interface PdfViewerProps {
  pdfUrl: string;
  projectTitle: string;
  hideTitle?: boolean;
}

const PdfViewer: React.FC<PdfViewerProps> = ({ pdfUrl, projectTitle, hideTitle = false }) => {
  const [numPages, setNumPages] = useState<number | null>(null);
  const [scale, setScale] = useState<number>(1.2);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [rotation, setRotation] = useState<number>(0);

  const onDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
    setNumPages(numPages);
    setLoading(false);
    setError(null);
  };

  const onDocumentLoadError = (error: Error) => {
    console.error('PDF 載入錯誤:', error);
    setError('無法載入 PDF 文件');
    setLoading(false);
  };

  const zoomIn = () => {
    setScale((prev) => Math.min(prev + 0.2, 2.5));
  };

  const zoomOut = () => {
    setScale((prev) => Math.max(prev - 0.2, 0.6));
  };

  const rotate = () => {
    setRotation((prev) => (prev + 90) % 360);
  };

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* Toolbar */}
      <div className="bg-white border-b border-gray-200 px-4 py-2 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-3">
          {!hideTitle && (
            <h3 className="text-base font-semibold text-gray-800 truncate max-w-md" title={projectTitle}>
              {projectTitle}
            </h3>
          )}
          {numPages && (
            <span className="text-xs text-gray-500 bg-gray-100 px-2 py-0.5 rounded">
              {numPages} 頁
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={zoomOut}
            disabled={scale <= 0.6}
            className="p-2 rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            title="縮小"
          >
            <FiZoomOut className="w-5 h-5" />
          </button>
          <span className="text-sm text-gray-600 min-w-[60px] text-center font-medium">
            {Math.round(scale * 100)}%
          </span>
          <button
            onClick={zoomIn}
            disabled={scale >= 2.5}
            className="p-2 rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            title="放大"
          >
            <FiZoomIn className="w-5 h-5" />
          </button>
          <div className="w-px h-6 bg-gray-300 mx-1"></div>
          <button
            onClick={rotate}
            className="p-2 rounded hover:bg-gray-100 transition-colors"
            title="旋轉"
          >
            <FiRotateCw className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* PDF Content */}
      <div className="flex-1 overflow-auto">
        {loading && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
              <p className="text-gray-600">載入中...</p>
            </div>
          </div>
        )}

        {error && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center text-red-600">
              <p className="text-lg font-semibold mb-2">載入失敗</p>
              <p className="text-sm">{error}</p>
              <p className="text-xs text-gray-500 mt-2">請檢查 PDF 文件路徑是否正確</p>
            </div>
          </div>
        )}

        {!error && (
          <div className="p-4">
            <Document
              file={pdfUrl}
              onLoadSuccess={onDocumentLoadSuccess}
              onLoadError={onDocumentLoadError}
              loading=""
              error=""
              className="flex flex-col items-center"
            >
              {Array.from({ length: numPages ?? 0 }, (_, index) => (
                <div key={`page_${index + 1}`} className="pdf-page-container mb-6">
                  <Page
                    pageNumber={index + 1}
                    scale={scale}
                    rotate={rotation}
                    renderTextLayer={false}
                    renderAnnotationLayer={false}
                    loading={
                      <div className="flex items-center justify-center p-8">
                        <div className="animate-pulse text-gray-400">載入第 {index + 1} 頁...</div>
                      </div>
                    }
                  />
                  <div className="text-center py-1.5 text-xs text-gray-400 bg-white border-t border-gray-200">
                    {index + 1} / {numPages}
                  </div>
                </div>
              ))}
            </Document>
          </div>
        )}
      </div>
    </div>
  );
};

export default PdfViewer;
