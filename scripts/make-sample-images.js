'use strict';
// Generates the sample PNG images used by the project templates (no image libraries needed).
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const { crc32 } = require('../server/zip');

function png(width, height, pixel) {
  const raw = Buffer.alloc((width * 3 + 1) * height);
  let o = 0;
  for (let y = 0; y < height; y++) {
    raw[o++] = 0;
    for (let x = 0; x < width; x++) {
      const [r, g, b] = pixel(x, y);
      raw[o++] = r;
      raw[o++] = g;
      raw[o++] = b;
    }
  }
  const chunk = (type, data) => {
    const len = Buffer.alloc(4);
    len.writeUInt32BE(data.length);
    const td = Buffer.concat([Buffer.from(type), data]);
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(crc32(td));
    return Buffer.concat([len, td, crc]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = 2;
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', zlib.deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

const mix = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * Math.min(1, Math.max(0, t))));

function landscape(x, y, W, H) {
  const sky = mix([255, 214, 170], [120, 170, 230], 1 - y / (H * 0.65));
  let c = sky;
  const sx = W * 0.72, sy = H * 0.3, sr = H * 0.11;
  const d = Math.hypot(x - sx, y - sy);
  if (d < sr) c = [255, 240, 200];
  else if (d < sr * 1.6) c = mix([255, 230, 180], c, (d - sr) / (sr * 0.6));
  const m1 = H * 0.55 - Math.abs(((x / W) * 3.2) % 2 - 1) * H * 0.22 - Math.sin(x / 37) * 6;
  if (y > m1) c = mix([110, 120, 160], [80, 90, 130], (y - m1) / (H * 0.3));
  const m2 = H * 0.68 - Math.abs(((x / W + 0.3) * 2.1) % 2 - 1) * H * 0.18 - Math.sin(x / 23) * 4;
  if (y > m2) c = mix([70, 120, 90], [40, 85, 60], (y - m2) / (H * 0.3));
  const lake = H * 0.82;
  if (y > lake) c = mix([90, 140, 190], [50, 90, 140], (y - lake) / (H * 0.18));
  return c;
}

function chart(x, y, W, H) {
  // A simple bar-chart-like graphic in soft colours.
  let c = [250, 250, 252];
  if (y % 50 === 0) c = [225, 228, 235];
  const bars = [0.35, 0.6, 0.45, 0.8, 0.65];
  const colors = [[78, 121, 167], [242, 142, 43], [225, 87, 89], [118, 183, 178], [89, 161, 79]];
  const bw = W / (bars.length * 1.6);
  bars.forEach((h, i) => {
    const x0 = W * 0.08 + i * bw * 1.6;
    if (x >= x0 && x < x0 + bw && y > H * (0.92 - h * 0.85) && y < H * 0.92) c = colors[i];
  });
  if (Math.abs(y - H * 0.92) < 1.5 && x > W * 0.05 && x < W * 0.95) c = [60, 60, 70];
  return c;
}

function write(file, w, h, fn) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, png(w, h, (x, y) => fn(x, y, w, h)));
  console.log('wrote', file);
}

const T = path.join(__dirname, '..', 'server', 'templates');
for (const t of ['article', 'thesis', 'beamer']) {
  write(path.join(T, t, 'files', 'images', 'landscape.png'), 800, 500, landscape);
}
for (const t of ['article', 'thesis']) {
  write(path.join(T, t, 'files', 'images', 'chart.png'), 600, 400, chart);
}
