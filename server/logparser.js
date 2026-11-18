'use strict';
// Turns TeX / BibTeX / Biber logs into structured { level, file, line, message, content } entries.
const path = require('path');

const FILE_EXT =
  /\.(tex|ltx|sty|cls|clo|cfg|def|fd|aux|toc|lof|lot|bbl|ldf|lbx|cbx|bbx|dict|out|nav|snm|code\.tex|lua|bib|mkii|mkiv|w18|pgf|tikz|dat|csv|txt|ins|dtx|map|enc|tfm|pfb|vf|ist|gls|nls|idx|ind)$/i;

function normalizeFile(file, buildDir) {
  if (!file) return { file: null, external: false };
  let f = file.trim().replace(/^"|"$/g, '').replace(/\\/g, '/');
  const bd = buildDir ? buildDir.replace(/\\/g, '/') : null;
  if (bd && f.toLowerCase().startsWith(bd.toLowerCase())) f = f.slice(bd.length);
  f = f.replace(/^\/+/, '').replace(/^(\.\/)+/, '');
  const external = /^[a-zA-Z]:\//.test(f) || f.startsWith('/') || f.startsWith('../');
  return { file: f, external };
}

/** TeX wraps lines at 79 chars unless max_print_line is raised; glue wrapped lines back together. */
function unwrap(lines, width = 79) {
  const out = [];
  let buf = '';
  for (const l of lines) {
    buf += l;
    if (l.length === width) continue;
    out.push(buf);
    buf = '';
  }
  if (buf) out.push(buf);
  return out;
}

// "(C:/path with spaces/file.sty" | "(./chapters/intro.tex" | "(file.cfg" — optionally quoted.
const FILE_OPEN_RE = new RegExp(
  '^\\((?:"([^"]+)"|((?:[a-zA-Z]:[\\\\/]|\\.{1,2}[\\\\/]|/)[^()"\\n]*?' +
    FILE_EXT.source.replace(/^\\\.\(/, '\\.(?:').replace(/\$$/, '') +
    ')(?=[\\s)(\\[{<]|$)|([^()\\s"]+?\\.[A-Za-z0-9]{1,8})(?=[\\s)(\\[{<]|$))',
  'i'
);

function parseTexLog(text, buildDir) {
  const errors = [];
  const warnings = [];
  const typesetting = [];
  if (!text) return { errors, warnings, typesetting };
  const rawLines = text.split(/\r?\n/);
  const wrapped = rawLines.some((l) => l.length === 79);
  const lines = wrapped ? unwrap(rawLines) : rawLines;

  const stack = [];
  const currentFile = () => {
    for (let i = stack.length - 1; i >= 0; i--) if (stack[i]) return stack[i];
    return null;
  };
  const seen = new Set();
  const add = (arr, e) => {
    const n = normalizeFile(e.file, buildDir);
    const entry = { ...e, file: n.file, external: n.external };
    const key = `${entry.level}|${entry.file}|${entry.line}|${entry.message}`;
    if (seen.has(key)) return;
    seen.add(key);
    arr.push(entry);
  };

  const trackParens = (line) => {
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '(') {
        const m = FILE_OPEN_RE.exec(line.slice(i));
        const name = m && (m[1] || m[2] || m[3]);
        if (name && (FILE_EXT.test(name) || /[\\/]/.test(name))) {
          stack.push(name);
          i += m[0].length - 1;
        } else {
          stack.push(null);
        }
      } else if (ch === ')') {
        stack.pop();
      }
    }
  };

  const fileLineErr = /^((?:[a-zA-Z]:)?[^:]*?\.[A-Za-z0-9]+):(\d+): (.*)$/;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    let m;

    if ((m = fileLineErr.exec(line)) && !line.startsWith('!')) {
      const ctx = collectErrorContext(lines, i + 1);
      add(errors, { level: 'error', file: m[1], line: +m[2], message: m[3].trim(), content: ctx.text });
      i = ctx.end;
      continue;
    }

    if (line.startsWith('! ')) {
      const msg = line.slice(2).trim();
      const ctx = collectErrorContext(lines, i + 1);
      const ln = /^l\.(\d+)/m.exec(ctx.text);
      const dup = errors.some((e) => e.message === msg || (msg === 'Emergency stop.' && errors.length));
      if (!dup) add(errors, { level: 'error', file: currentFile(), line: ln ? +ln[1] : null, message: msg, content: ctx.text });
      i = ctx.end;
      continue;
    }

    if ((m = /^(LaTeX|Package ([\w.@-]+)|Class ([\w.@-]+)|pdfTeX|LaTeX Font|Module ([\w.@-]+)) Warning: (.*)$/.exec(line))) {
      let msg = m[5];
      const pkg = m[2] || m[3] || m[4] || (m[1] === 'LaTeX Font' ? 'Font' : null);
      let j = i + 1;
      while (j < lines.length) {
        const cont = lines[j];
        const pm = /^\(([\w.@-]+)\)\s+(.*)$/.exec(cont);
        if (pm && (!pkg || pm[1] === pkg || pkg === 'Font')) {
          msg += ' ' + pm[2];
          j++;
        } else if ((m[1] === 'LaTeX' || m[1] === 'pdfTeX') && /^\s{8,}\S/.test(cont)) {
          msg += ' ' + cont.trim();
          j++;
        } else break;
      }
      i = j - 1;
      const ln = /on input line (\d+)/.exec(msg) || /at lines? (\d+)/.exec(msg);
      const prefix = m[1] === 'LaTeX' ? '' : (pkg ? (m[1].startsWith('Class') ? `Class ${pkg}: ` : m[1].startsWith('Package') ? `Package ${pkg}: ` : `${m[1]}: `) : `${m[1]}: `);
      const level = m[1] === 'LaTeX Font' ? 'typesetting' : 'warning';
      add(level === 'warning' ? warnings : typesetting, {
        level,
        file: currentFile(),
        line: ln ? +ln[1] : null,
        message: prefix + msg.trim(),
      });
      trackParens(line);
      continue;
    }

    if ((m = /^(Overfull|Underfull) \\([hv])box (.*)$/.exec(line))) {
      const ln = /at lines? (\d+)/.exec(line);
      const detail = lines[i + 1] && !lines[i + 1].startsWith('[') ? lines[i + 1].trim() : '';
      add(typesetting, {
        level: 'typesetting',
        file: currentFile(),
        line: ln ? +ln[1] : null,
        message: `${m[1]} \\${m[2]}box ${m[3]}`.replace(/\s+/g, ' ').trim(),
        content: detail,
      });
      continue;
    }

    if ((m = /^Missing character: (.*)$/.exec(line))) {
      add(warnings, { level: 'warning', file: currentFile(), line: null, message: 'Missing character: ' + m[1] });
      continue;
    }

    trackParens(line);
  }
  return { errors, warnings, typesetting };
}

function collectErrorContext(lines, start) {
  const out = [];
  let j = start;
  let sawL = false;
  for (; j < lines.length && out.length < 14; j++) {
    const l = lines[j];
    if (sawL) {
      out.push(l);
      break;
    }
    if (/^l\.\d+/.test(l)) {
      out.push(l);
      sawL = true;
      continue;
    }
    if (l.trim() === '' && out.length > 0 && !sawL) {
      // blank lines appear inside some messages; stop only if next line looks unrelated
      if (j + 1 < lines.length && !/^l\.\d+|^\s|^\S.*\.$/.test(lines[j + 1])) break;
    }
    if (/^(\.\/|[a-zA-Z]:\/).*:\d+: /.test(l) || l.startsWith('! ')) {
      j--;
      break;
    }
    out.push(l);
  }
  return { text: out.join('\n').trim(), end: Math.min(j, lines.length - 1) };
}

function parseBibtexLog(text, buildDir) {
  const errors = [];
  const warnings = [];
  if (!text) return { errors, warnings };
  const lines = text.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    let m;
    if ((m = /^Warning--(.*)$/.exec(l))) {
      const next = lines[i + 1] || '';
      const loc = /^--line (\d+) of file (.*)$/.exec(next);
      warnings.push({
        level: 'warning',
        file: loc ? normalizeFile(loc[2], buildDir).file : null,
        line: loc ? +loc[1] : null,
        message: 'BibTeX: ' + m[1],
      });
    } else if ((m = /^(.*)---line (\d+) of file (.*)$/.exec(l))) {
      errors.push({ level: 'error', file: normalizeFile(m[3], buildDir).file, line: +m[2], message: 'BibTeX: ' + m[1].trim(), content: lines.slice(i + 1, i + 4).join('\n') });
    } else if (/^I couldn't open (database|style) file/.test(l) || /^I found no \\(bibdata|bibstyle|citation)/.test(l)) {
      errors.push({ level: 'error', file: null, line: null, message: 'BibTeX: ' + l.trim() });
    }
  }
  return { errors, warnings };
}

function parseBiberLog(text, buildDir) {
  const errors = [];
  const warnings = [];
  if (!text) return { errors, warnings };
  for (const l of text.split(/\r?\n/)) {
    const m = /\b(WARN|ERROR) - (.*)$/.exec(l);
    if (!m) continue;
    const msg = m[2].trim();
    const fm = /([^\\/\s:]+\.bib)/i.exec(msg);
    const lm = /line (\d+)/.exec(msg);
    const entry = {
      level: m[1] === 'ERROR' ? 'error' : 'warning',
      file: fm ? fm[1] : null,
      line: lm ? +lm[1] : null,
      message: 'Biber: ' + msg.replace(/\S+\.bib_\d+\.utf8/g, fm ? fm[1] : 'bib file'),
      bibBasename: !!fm,
    };
    (entry.level === 'error' ? errors : warnings).push(entry);
  }
  return { errors, warnings };
}

module.exports = { parseTexLog, parseBibtexLog, parseBiberLog };
