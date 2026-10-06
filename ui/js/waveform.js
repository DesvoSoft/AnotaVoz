// Rolling bar waveform on a <canvas>; push(level 0..1) per level event.
export class Waveform {
  constructor(canvas, cssVar) {
    this.c = canvas; this.ctx = canvas.getContext('2d'); this.cssVar = cssVar;
    this.bars = new Array(64).fill(0); this.target = 0; this.raf = null;
    this.resize(); new ResizeObserver(() => this.resize()).observe(canvas);
  }
  resize() {
    const r = devicePixelRatio || 1, w = this.c.clientWidth, h = this.c.clientHeight;
    if (!w || !h) return;
    this.c.width = w * r; this.c.height = h * r; this.ctx.setTransform(r, 0, 0, r, 0, 0);
    this.draw();
  }
  push(v) { this.target = Math.min(1, Math.sqrt(v) * 1.6); }
  start() { if (!this.raf) { const loop = () => { this.step(); this.raf = requestAnimationFrame(loop); }; loop(); } }
  stop() { cancelAnimationFrame(this.raf); this.raf = null; this.bars.fill(0); this.target = 0; this.draw(); }
  step() { this.bars.shift(); this.bars.push(this.target); this.target *= 0.85; this.draw(); }
  draw() {
    const { ctx, bars } = this, w = this.c.clientWidth, h = this.c.clientHeight;
    ctx.clearRect(0, 0, w, h);
    const gap = 3, bw = Math.max(1, (w - gap * (bars.length - 1)) / bars.length);
    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue(this.cssVar).trim() || '#5b8def';
    bars.forEach((b, i) => {
      const bh = Math.max(3, b * h), x = i * (bw + gap), y = (h - bh) / 2;
      ctx.beginPath(); ctx.roundRect(x, y, bw, bh, bw / 2); ctx.fill();
    });
  }
}
