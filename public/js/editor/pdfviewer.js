// PDF preview built on PDF.js: lazy page rendering, zoom, flicker-free reloads, SyncTeX hooks.
import * as pdfjsLib from '/vendor/pdfjs/pdf.min.mjs';

pdfjsLib.GlobalWorkerOptions.workerSrc = '/vendor/pdfjs/pdf.worker.min.mjs';

const CSS_UNITS = 96 / 72;
const ZOOM_STEPS = [0.25, 0.33, 0.5, 0.67, 0.75, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3, 4];

export class PdfViewer {
  constructor(scrollEl, { onDoubleClick, onChange } = {}) {
    this.scrollEl = scrollEl;
    this.pagesEl = document.createElement('div');
    this.pagesEl.className = 'pdf-pages';
    scrollEl.appendChild(this.pagesEl);
    this.onDoubleClick = onDoubleClick;
    this.onChange = onChange || (() => {});
    this.doc = null;
    this.pages = []; // { el, pdfPage, w, h (points), renderedScale, task }
    this.mode = localStorage.getItem('folio.pdfZoomMode') || 'page-width';
    this.zoom = +localStorage.getItem('folio.pdfZoom') || 1; // used when mode === 'custom'
    this.scale = 1; // CSS px per PDF point
    this.visible = new Set();
    this.generation = 0;

    this.observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          const idx = +e.target.dataset.index;
          if (e.isIntersecting) this.visible.add(idx);
          else this.visible.delete(idx);
        }
        this.renderVisible();
      },
      { root: scrollEl, rootMargin: '300px 0px' }
    );

    new ResizeObserver(() => {
      clearTimeout(this._rz);
      this._rz = setTimeout(() => {
        if (this.mode !== 'custom' && this.doc) this.relayout(true);
      }, 80);
    }).observe(scrollEl);

    scrollEl.addEventListener('scroll', () => this.onChange());
    scrollEl.addEventListener(
      'wheel',
      (e) => {
        if (!e.ctrlKey || !this.doc) return;
        e.preventDefault();
        this.setZoom(this.currentZoom() * (e.deltaY < 0 ? 1.1 : 1 / 1.1), { x: e.clientX, y: e.clientY });
      },
      { passive: false }
    );
    this.pagesEl.addEventListener('dblclick', (e) => {
      const pageEl = e.target.closest('.pdf-page');
      if (!pageEl || !this.onDoubleClick) return;
      const r = pageEl.getBoundingClientRect();
      const x = (e.clientX - r.left) / this.scale;
      const y = (e.clientY - r.top) / this.scale;
      window.getSelection()?.removeAllRanges();
      this.onDoubleClick(+pageEl.dataset.index + 1, x, y);
    });
  }

  get numPages() {
    return this.doc ? this.doc.numPages : 0;
  }

  currentZoom() {
    return this.scale / CSS_UNITS;
  }

  currentPage() {
    if (!this.pages.length) return 0;
    const top = this.scrollEl.scrollTop + this.scrollEl.clientHeight / 3;
    for (let i = 0; i < this.pages.length; i++) {
      const el = this.pages[i].el;
      if (el.offsetTop + el.offsetHeight > top) return i + 1;
    }
    return this.pages.length;
  }

  /** Position as page index + fraction, so it survives recompiles and zoom changes. */
  getPosition() {
    if (!this.pages.length) return null;
    const st = this.scrollEl.scrollTop;
    for (let i = 0; i < this.pages.length; i++) {
      const el = this.pages[i].el;
      if (el.offsetTop + el.offsetHeight > st) {
        return { page: i, frac: (st - el.offsetTop) / el.offsetHeight, left: this.scrollEl.scrollLeft };
      }
    }
    return { page: this.pages.length - 1, frac: 0, left: 0 };
  }

  setPosition(pos) {
    if (!pos || !this.pages.length) return;
    const p = this.pages[Math.min(pos.page, this.pages.length - 1)];
    this.scrollEl.scrollTop = p.el.offsetTop + pos.frac * p.el.offsetHeight;
    this.scrollEl.scrollLeft = pos.left || 0;
  }

  async load(url) {
    const gen = ++this.generation;
    const data = await fetch(url, { cache: 'no-store' }).then((r) => {
      if (!r.ok) throw new Error('Could not load PDF');
      return r.arrayBuffer();
    });
    const doc = await pdfjsLib.getDocument({
      data,
      cMapUrl: '/vendor/pdfjs-cmaps/',
      cMapPacked: true,
      standardFontDataUrl: '/vendor/pdfjs-fonts/',
    }).promise;
    if (gen !== this.generation) {
      doc.destroy();
      return;
    }
    const pos = this.getPosition();
    const old = this.doc;
    this.doc = doc;
    const pdfPages = await Promise.all(Array.from({ length: doc.numPages }, (_, i) => doc.getPage(i + 1)));

    // Reuse existing page elements so the old rendering stays visible until the new one is ready.
    while (this.pages.length > pdfPages.length) {
      const p = this.pages.pop();
      this.observer.unobserve(p.el);
      p.el.remove();
    }
    pdfPages.forEach((pp, i) => {
      const vp = pp.getViewport({ scale: 1 });
      let p = this.pages[i];
      if (!p) {
        const el = document.createElement('div');
        el.className = 'pdf-page';
        el.dataset.index = i;
        this.pagesEl.appendChild(el);
        p = { el };
        this.pages.push(p);
        this.observer.observe(el);
      }
      if (p.task) p.task.cancel();
      Object.assign(p, { pdfPage: pp, w: vp.width, h: vp.height, renderedScale: 0, task: null, stale: true });
    });
    this.relayout(false);
    if (pos) this.setPosition(pos);
    this.renderVisible();
    if (old) setTimeout(() => old.destroy(), 1500);
    this.onChange();
  }

  clear() {
    this.generation++;
    for (const p of this.pages) {
      this.observer.unobserve(p.el);
      p.el.remove();
    }
    this.pages = [];
    this.doc?.destroy();
    this.doc = null;
    this.onChange();
  }

  computeScale() {
    if (!this.pages.length) return this.scale;
    const avail = this.scrollEl.clientWidth - 28 - 2;
    const maxW = Math.max(...this.pages.map((p) => p.w));
    if (this.mode === 'page-width') return Math.max(0.1, avail / maxW);
    if (this.mode === 'page-fit') {
      const p = this.pages[0];
      return Math.max(0.1, Math.min(avail / p.w, (this.scrollEl.clientHeight - 28) / p.h));
    }
    return this.zoom * CSS_UNITS;
  }

  relayout(keepPosition = true) {
    const pos = keepPosition ? this.getPosition() : null;
    this.scale = this.computeScale();
    for (const p of this.pages) {
      p.el.style.width = Math.floor(p.w * this.scale) + 'px';
      p.el.style.height = Math.floor(p.h * this.scale) + 'px';
    }
    if (pos) this.setPosition(pos);
    this.renderVisible();
    this.onChange();
  }

  setZoom(z, anchor) {
    z = Math.min(5, Math.max(0.1, z));
    this.mode = 'custom';
    this.zoom = z;
    this.persist();
    this.relayout(true);
  }
  setMode(mode) {
    this.mode = mode;
    this.persist();
    this.relayout(true);
  }
  zoomIn() {
    const z = this.currentZoom();
    this.setZoom(ZOOM_STEPS.find((s) => s > z + 0.01) || z * 1.25);
  }
  zoomOut() {
    const z = this.currentZoom();
    this.setZoom([...ZOOM_STEPS].reverse().find((s) => s < z - 0.01) || z / 1.25);
  }
  persist() {
    try {
      localStorage.setItem('folio.pdfZoomMode', this.mode);
      localStorage.setItem('folio.pdfZoom', String(this.zoom));
    } catch {
      /* ignore */
    }
  }

  renderVisible() {
    for (const idx of this.visible) this.renderPage(idx);
  }

  async renderPage(idx) {
    const p = this.pages[idx];
    if (!p || !p.pdfPage) return;
    const dpr = window.devicePixelRatio || 1;
    const target = this.scale * dpr;
    if (!p.stale && Math.abs(p.renderedScale - target) < 0.001) return;
    if (p.task) {
      if (p.taskScale === target && p.taskPage === p.pdfPage) return;
      p.task.cancel();
    }
    const vp = p.pdfPage.getViewport({ scale: target });
    const canvas = document.createElement('canvas');
    canvas.width = Math.ceil(vp.width);
    canvas.height = Math.ceil(vp.height);
    const task = p.pdfPage.render({ canvasContext: canvas.getContext('2d', { alpha: false }), viewport: vp });
    p.task = task;
    p.taskScale = target;
    p.taskPage = p.pdfPage;
    try {
      await task.promise;
      const old = p.el.querySelector('canvas');
      if (old) old.replaceWith(canvas);
      else p.el.prepend(canvas);
      p.renderedScale = target;
      p.stale = false;
    } catch (e) {
      if (e?.name !== 'RenderingCancelledException') console.warn(e);
    } finally {
      if (p.task === task) p.task = null;
    }
  }

  /** Highlight SyncTeX boxes and scroll the first into view. Boxes are in PDF points (top-left origin). */
  highlight(boxes) {
    if (!boxes.length) return;
    let first = null;
    for (const b of boxes) {
      const p = this.pages[b.page - 1];
      if (!p) continue;
      const w = b.width > 0 ? b.width : p.w * 0.8;
      const hgt = b.height > 0 ? b.height : 12;
      const left = b.width > 0 ? b.h : p.w * 0.1;
      const top = b.v - hgt;
      const el = document.createElement('div');
      el.className = 'sync-hl';
      el.style.left = left * this.scale + 'px';
      el.style.top = top * this.scale + 'px';
      el.style.width = w * this.scale + 'px';
      el.style.height = Math.max(hgt * this.scale, 6) + 'px';
      p.el.appendChild(el);
      setTimeout(() => el.remove(), 2600);
      if (!first) first = { p, top };
    }
    if (first) {
      const y = first.p.el.offsetTop + first.top * this.scale - this.scrollEl.clientHeight / 3;
      this.scrollEl.scrollTo({ top: Math.max(0, y), behavior: 'smooth' });
    }
  }

  goToPage(n) {
    const p = this.pages[n - 1];
    if (p) this.scrollEl.scrollTop = p.el.offsetTop - 10;
  }
}
