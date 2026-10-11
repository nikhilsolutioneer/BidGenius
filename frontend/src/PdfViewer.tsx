import { useEffect, useRef, useState } from 'react';
import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist';
import type { PDFDocumentProxy, PDFDocumentLoadingTask } from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Plus,
  ZoomIn,
  ZoomOut,
  FileText,
  MousePointer2,
} from 'lucide-react';
import { api } from './api';
import { Button, ErrorBox, Spinner } from './components';
import type { Document, SourceSpan } from './types';
GlobalWorkerOptions.workerSrc = workerUrl;
export default function PdfViewer({
  document,
  page: initialPage,
  highlightIds,
  onCreate,
}: {
  document: Document;
  page: number;
  highlightIds: string[];
  onCreate: (spans: SourceSpan[]) => void;
}) {
  const [page, setPage] = useState(initialPage);
  const [spans, setSpans] = useState<SourceSpan[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [zoom, setZoom] = useState(1);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [size, setSize] = useState({ width: 595, height: 842 });
  const [availableWidth, setAvailableWidth] = useState(370);
  const canvas = useRef<HTMLCanvasElement>(null);
  const container = useRef<HTMLDivElement>(null);
  // Keep the loaded document separate from each page's cancellable render.
  // Reusing a loading-task ref here can leave a page waiting forever when a
  // render effect is recreated by the inspector resize/zoom lifecycle.
  const pdfTask = useRef<PDFDocumentLoadingTask | null>(null);
  const pdfDocument = useRef<PDFDocumentProxy | null>(null);
  const pdfLoading = useRef<Promise<PDFDocumentProxy> | null>(null);
  useEffect(() => {
    setPage(initialPage);
    setSelected([]);
  }, [initialPage, document.id]);
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver((entries) =>
      setAvailableWidth(Math.max(240, entries[0].contentRect.width - 24)),
    );
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    let cancelled = false;
    const task = getDocument(`/api/documents/${document.id}/file`);
    pdfTask.current = task;
    pdfDocument.current = null;
    pdfLoading.current = task.promise;
    void pdfLoading.current.then((loaded) => {
      if (cancelled) {
        void loaded.destroy();
        return;
      }
      pdfDocument.current = loaded;
    }).catch(() => {
      // The page effect below reports the actual loading error in the UI.
    });
    return () => {
      cancelled = true;
      const loaded = pdfDocument.current;
      pdfDocument.current = null;
      pdfLoading.current = null;
      pdfTask.current = null;
      if (loaded) {
        void loaded.destroy();
      } else {
        void task.destroy();
      }
    };
  }, [document.id]);
  useEffect(() => {
    let dead = false;
    let renderTask: { cancel: () => void } | null = null;
    setLoading(true);
    setError('');
    setSelected([]);
    setSpans([]);
    const work = async () => {
      try {
        const [doc, data] = await Promise.all([
          pdfLoading.current ?? Promise.reject(new Error('PDF loading task is unavailable')),
          api<{ items: SourceSpan[]; width: number; height: number }>(
            `/documents/${document.id}/pages/${page}/spans`,
          ),
        ]);
        if (dead) return;
        setSpans(data.items);
        const p = await doc.getPage(page);
        if (dead) return;
        const original = p.getViewport({ scale: 1 });
        const scale = (availableWidth / original.width) * zoom;
        const viewport = p.getViewport({ scale });
        setSize((current) =>
          Math.abs(current.width - viewport.width) < 0.5 && Math.abs(current.height - viewport.height) < 0.5
            ? current
            : { width: viewport.width, height: viewport.height },
        );
        const el = canvas.current;
        if (!el) {
          if (!dead) setLoading(false);
          return;
        }
        const pixelRatio = window.devicePixelRatio || 1;
        el.width = viewport.width * pixelRatio;
        el.height = viewport.height * pixelRatio;
        const ctx = el.getContext('2d');
        if (!ctx) {
          if (!dead) {
            setError('Unable to render this PDF page in the browser.');
            setLoading(false);
          }
          return;
        }
        renderTask = p.render({
          canvasContext: ctx,
          viewport,
          transform: pixelRatio !== 1 ? [pixelRatio, 0, 0, pixelRatio, 0, 0] : undefined,
        });
        await (renderTask as unknown as { promise: Promise<void> }).promise;
        if (!dead) setLoading(false);
      } catch (e) {
        if (!dead && (e as Error).name !== 'RenderingCancelledException') {
          setError((e as Error).message);
          setLoading(false);
        }
      }
    };
    void work();
    return () => {
      dead = true;
      renderTask?.cancel();
    };
  }, [document.id, page, availableWidth, zoom]);
  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  return (
    <div className="pdf-viewer">
      <div className="pdf-toolbar">
        <div className="inline">
          <button
            className="icon-btn"
            aria-label="Previous PDF page"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            <ChevronLeft size={16} />
          </button>
          <label className="page-input">
            <span className="sr-only">PDF page</span>
            <input
              type="number"
              min={1}
              max={document.page_count}
              value={page}
              onChange={(e) => {
                const n = Number(e.target.value);
                if (n >= 1 && n <= document.page_count) setPage(n);
              }}
            />
            <span>/ {document.page_count}</span>
          </label>
          <button
            className="icon-btn"
            aria-label="Next PDF page"
            disabled={page >= document.page_count}
            onClick={() => setPage((p) => p + 1)}
          >
            <ChevronRight size={16} />
          </button>
        </div>
        <div className="inline">
          <button
            className="icon-btn"
            aria-label="Zoom out"
            disabled={zoom <= 0.7}
            onClick={() => setZoom((z) => Math.max(0.7, z - 0.2))}
          >
            <ZoomOut size={16} />
          </button>
          <button
            className="icon-btn"
            aria-label="Zoom in"
            disabled={zoom >= 2}
            onClick={() => setZoom((z) => Math.min(2, z + 0.2))}
          >
            <ZoomIn size={16} />
          </button>
          <a
            className="icon-btn"
            href={`/api/documents/${document.id}/file#page=${page}`}
            target="_blank"
            rel="noreferrer"
            aria-label="Open original PDF"
          >
            <ExternalLink size={15} />
          </a>
        </div>
      </div>
      <div className="pdf-hint">
        <MousePointer2 size={13} /> Select evidence on the page to add a position
      </div>
      {error && <ErrorBox message={error} />}
      <div ref={container} className="pdf-scroll" tabIndex={0} aria-label="Scrollable source document">
        {loading && <Spinner text="Rendering source page…" />}
        <div
          className="pdf-sheet"
          aria-busy={loading}
          style={{ width: size.width, height: size.height }}
        >
          <canvas ref={canvas} style={{ width: size.width, height: size.height }} />
          {loading && (
            <div className="pdf-loading-overlay">
              <Spinner text="Rendering source page..." />
            </div>
          )}
          <div className="pdf-spans">
            {spans.map((s) => (
              <button
                key={s.id}
                title={s.text}
                aria-label={`Select evidence: ${s.text.slice(0, 80)}`}
                aria-pressed={selected.includes(s.id)}
                onClick={() => toggle(s.id)}
                className={`pdf-span ${highlightIds.includes(s.id) ? 'source-highlight' : ''} ${selected.includes(s.id) ? 'selected-span' : ''}`}
                style={{
                  left: `${(s.x0 / s.page_width) * 100}%`,
                  top: `${(s.top / s.page_height) * 100}%`,
                  width: `${((s.x1 - s.x0) / s.page_width) * 100}%`,
                  height: `${((s.bottom - s.top) / s.page_height) * 100}%`,
                }}
              />
            ))}
          </div>
        </div>
      </div>
      <div className="source-selection">
        <div className="section-label">
          <FileText size={13} /> SOURCE TEXT · PAGE {page}
        </div>
        <div className="source-text-list">
          {spans
            .filter((s) => highlightIds.includes(s.id) || selected.includes(s.id))
            .map((s) => (
              <button
                key={s.id}
                className={selected.includes(s.id) ? 'selected' : ''}
                translate="no"
                lang="de"
                aria-pressed={selected.includes(s.id)}
                onClick={() => toggle(s.id)}
              >
                {s.text}
              </button>
            ))}
          {!spans.some((s) => highlightIds.includes(s.id) || selected.includes(s.id)) && (
            <p>Click a source region above to inspect its original text.</p>
          )}
        </div>
        <Button
          variant="primary"
          disabled={!selected.length}
          onClick={() => onCreate(spans.filter((s) => selected.includes(s.id)))}
        >
          <Plus size={15} /> Create position from selection {selected.length > 0 && `(${selected.length})`}
        </Button>
      </div>
    </div>
  );
}
