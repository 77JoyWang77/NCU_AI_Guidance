interface PdfViewerProps {
  pdfUrl: string;
  projectTitle: string;
  hideTitle?: boolean;
}

export default function PdfViewer({ pdfUrl }: PdfViewerProps) {
  return (
    <iframe
      src={pdfUrl}
      title="PDF 文件"
      className="h-full w-full border-0"
    />
  );
}
