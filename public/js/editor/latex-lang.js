// LaTeX + BibTeX language support for Monaco: highlighting, completion, hovers, themes.

const MATH_ENVS = 'equation|align|gather|multline|flalign|alignat|eqnarray|displaymath|math|dmath';
const VERB_ENVS = 'verbatim|Verbatim|lstlisting|minted|comment|filecontents';

export const ENVIRONMENTS = [
  ['figure', '\\begin{figure}[htbp]\n\t\\centering\n\t\\includegraphics[width=0.8\\linewidth]{${1:file}}\n\t\\caption{${2:Caption}}\n\t\\label{fig:${3:label}}\n\\end{figure}'],
  ['table', '\\begin{table}[htbp]\n\t\\centering\n\t\\caption{${1:Caption}}\n\t\\label{tab:${2:label}}\n\t\\begin{tabular}{${3:lcr}}\n\t\t\\toprule\n\t\t${4:A} & ${5:B} & ${6:C} \\\\\\\\\n\t\t\\midrule\n\t\t$0 \\\\\\\\\n\t\t\\bottomrule\n\t\\end{tabular}\n\\end{table}'],
  ['tabular', '\\begin{tabular}{${1:lcr}}\n\t$0\n\\end{tabular}'],
  ['itemize', '\\begin{itemize}\n\t\\item $0\n\\end{itemize}'],
  ['enumerate', '\\begin{enumerate}\n\t\\item $0\n\\end{enumerate}'],
  ['description', '\\begin{description}\n\t\\item[${1:term}] $0\n\\end{description}'],
  ['equation', '\\begin{equation}\n\t$0\n\t\\label{eq:${1:label}}\n\\end{equation}'],
  ['equation*', '\\begin{equation*}\n\t$0\n\\end{equation*}'],
  ['align', '\\begin{align}\n\t$0\n\\end{align}'],
  ['align*', '\\begin{align*}\n\t$0\n\\end{align*}'],
  ['gather', '\\begin{gather}\n\t$0\n\\end{gather}'],
  ['multline', '\\begin{multline}\n\t$0\n\\end{multline}'],
  ['cases', '\\begin{cases}\n\t${1:a} & \\text{if } ${2:x > 0} \\\\\\\\\n\t$0\n\\end{cases}'],
  ['pmatrix', '\\begin{pmatrix}\n\t$0\n\\end{pmatrix}'],
  ['bmatrix', '\\begin{bmatrix}\n\t$0\n\\end{bmatrix}'],
  ['matrix', '\\begin{matrix}\n\t$0\n\\end{matrix}'],
  ['center', '\\begin{center}\n\t$0\n\\end{center}'],
  ['flushleft', '\\begin{flushleft}\n\t$0\n\\end{flushleft}'],
  ['flushright', '\\begin{flushright}\n\t$0\n\\end{flushright}'],
  ['minipage', '\\begin{minipage}{${1:0.45\\linewidth}}\n\t$0\n\\end{minipage}'],
  ['subfigure', '\\begin{subfigure}[b]{${1:0.45\\linewidth}}\n\t\\centering\n\t\\includegraphics[width=\\linewidth]{${2:file}}\n\t\\caption{${3:Caption}}\n\t\\label{fig:${4:label}}\n\\end{subfigure}'],
  ['tikzpicture', '\\begin{tikzpicture}\n\t$0\n\\end{tikzpicture}'],
  ['axis', '\\begin{axis}[xlabel={${1:\\$x\\$}}, ylabel={${2:\\$y\\$}}]\n\t\\addplot {${3:x^2}};\n\\end{axis}'],
  ['abstract', '\\begin{abstract}\n\t$0\n\\end{abstract}'],
  ['quote', '\\begin{quote}\n\t$0\n\\end{quote}'],
  ['verbatim', '\\begin{verbatim}\n$0\n\\end{verbatim}'],
  ['lstlisting', '\\begin{lstlisting}[language=${1:Python}]\n$0\n\\end{lstlisting}'],
  ['minted', '\\begin{minted}{${1:python}}\n$0\n\\end{minted}'],
  ['theorem', '\\begin{theorem}\n\t$0\n\\end{theorem}'],
  ['lemma', '\\begin{lemma}\n\t$0\n\\end{lemma}'],
  ['definition', '\\begin{definition}\n\t$0\n\\end{definition}'],
  ['proof', '\\begin{proof}\n\t$0\n\\end{proof}'],
  ['frame', '\\begin{frame}{${1:Title}}\n\t$0\n\\end{frame}'],
  ['block', '\\begin{block}{${1:Title}}\n\t$0\n\\end{block}'],
  ['columns', '\\begin{columns}\n\t\\begin{column}{0.5\\textwidth}\n\t\t$0\n\t\\end{column}\n\t\\begin{column}{0.5\\textwidth}\n\t\\end{column}\n\\end{columns}'],
  ['column', '\\begin{column}{${1:0.5\\textwidth}}\n\t$0\n\\end{column}'],
  ['document', '\\begin{document}\n$0\n\\end{document}'],
  ['thebibliography', '\\begin{thebibliography}{9}\n\t\\bibitem{${1:key}} $0\n\\end{thebibliography}'],
  ['appendices', '\\begin{appendices}\n$0\n\\end{appendices}'],
  ['titlepage', '\\begin{titlepage}\n\t$0\n\\end{titlepage}'],
  ['landscape', '\\begin{landscape}\n\t$0\n\\end{landscape}'],
  ['wrapfigure', '\\begin{wrapfigure}{r}{${1:0.4\\textwidth}}\n\t\\centering\n\t\\includegraphics[width=\\linewidth]{${2:file}}\n\t\\caption{${3:Caption}}\n\\end{wrapfigure}'],
];

// [name, snippet (without leading backslash), detail]
const COMMANDS = [
  ['section', 'section{${1:title}}', 'Section'],
  ['section*', 'section*{${1:title}}', 'Unnumbered section'],
  ['subsection', 'subsection{${1:title}}', 'Subsection'],
  ['subsubsection', 'subsubsection{${1:title}}', 'Subsubsection'],
  ['chapter', 'chapter{${1:title}}', 'Chapter'],
  ['part', 'part{${1:title}}', 'Part'],
  ['paragraph', 'paragraph{${1:title}}', 'Paragraph'],
  ['begin', 'begin{${1:env}}\n\t$0\n\\end{${1:env}}', 'Environment'],
  ['textbf', 'textbf{${1:text}}', 'Bold'],
  ['textit', 'textit{${1:text}}', 'Italic'],
  ['emph', 'emph{${1:text}}', 'Emphasis'],
  ['underline', 'underline{${1:text}}', 'Underline'],
  ['texttt', 'texttt{${1:text}}', 'Monospace'],
  ['textsc', 'textsc{${1:text}}', 'Small caps'],
  ['textcolor', 'textcolor{${1:red}}{${2:text}}', 'Coloured text'],
  ['footnote', 'footnote{${1:text}}', 'Footnote'],
  ['label', 'label{${1:key}}', 'Label'],
  ['ref', 'ref{${1}}', 'Reference'],
  ['eqref', 'eqref{${1}}', 'Equation reference'],
  ['cref', 'cref{${1}}', 'Clever reference'],
  ['Cref', 'Cref{${1}}', 'Clever reference (capitalised)'],
  ['autoref', 'autoref{${1}}', 'Auto reference'],
  ['pageref', 'pageref{${1}}', 'Page reference'],
  ['cite', 'cite{${1}}', 'Citation'],
  ['citep', 'citep{${1}}', 'natbib parenthetical'],
  ['citet', 'citet{${1}}', 'natbib textual'],
  ['autocite', 'autocite{${1}}', 'biblatex citation'],
  ['parencite', 'parencite{${1}}', 'biblatex parenthetical'],
  ['textcite', 'textcite{${1}}', 'biblatex textual'],
  ['footcite', 'footcite{${1}}', 'biblatex footnote citation'],
  ['includegraphics', 'includegraphics[width=${1:0.8}\\linewidth]{${2}}', 'Insert image'],
  ['input', 'input{${1}}', 'Input file'],
  ['include', 'include{${1}}', 'Include file'],
  ['usepackage', 'usepackage{${1}}', 'Load package'],
  ['documentclass', 'documentclass{${1:article}}', 'Document class'],
  ['addbibresource', 'addbibresource{${1:references.bib}}', 'biblatex bibliography file'],
  ['bibliography', 'bibliography{${1:references}}', 'BibTeX bibliography'],
  ['bibliographystyle', 'bibliographystyle{${1:plain}}', 'BibTeX style'],
  ['printbibliography', 'printbibliography', 'Print bibliography'],
  ['caption', 'caption{${1:text}}', 'Caption'],
  ['centering', 'centering', ''],
  ['item', 'item ', 'List item'],
  ['maketitle', 'maketitle', ''],
  ['tableofcontents', 'tableofcontents', ''],
  ['listoffigures', 'listoffigures', ''],
  ['listoftables', 'listoftables', ''],
  ['title', 'title{${1}}', ''],
  ['author', 'author{${1}}', ''],
  ['date', 'date{${1:\\today}}', ''],
  ['today', 'today', ''],
  ['newpage', 'newpage', ''],
  ['clearpage', 'clearpage', ''],
  ['newline', 'newline', ''],
  ['noindent', 'noindent', ''],
  ['vspace', 'vspace{${1:1em}}', ''],
  ['hspace', 'hspace{${1:1em}}', ''],
  ['hfill', 'hfill', ''],
  ['vfill', 'vfill', ''],
  ['url', 'url{${1}}', 'URL'],
  ['href', 'href{${1:https://}}{${2:text}}', 'Hyperlink'],
  ['newcommand', 'newcommand{\\\\${1:name}}[${2:1}]{${3}}', 'Define command'],
  ['renewcommand', 'renewcommand{\\\\${1:name}}{${2}}', ''],
  ['frac', 'frac{${1}}{${2}}', 'Fraction'],
  ['dfrac', 'dfrac{${1}}{${2}}', 'Display fraction'],
  ['sqrt', 'sqrt{${1}}', 'Square root'],
  ['sum', 'sum_{${1:i=1}}^{${2:n}}', 'Sum'],
  ['prod', 'prod_{${1:i=1}}^{${2:n}}', 'Product'],
  ['int', 'int_{${1:a}}^{${2:b}}', 'Integral'],
  ['iint', 'iint', ''],
  ['oint', 'oint', ''],
  ['lim', 'lim_{${1:n \\to \\infty}}', 'Limit'],
  ['infty', 'infty', '∞'],
  ['partial', 'partial', '∂'],
  ['nabla', 'nabla', '∇'],
  ['cdot', 'cdot', '·'],
  ['cdots', 'cdots', '⋯'],
  ['ldots', 'ldots', '…'],
  ['times', 'times', '×'],
  ['leq', 'leq', '≤'],
  ['geq', 'geq', '≥'],
  ['neq', 'neq', '≠'],
  ['approx', 'approx', '≈'],
  ['equiv', 'equiv', '≡'],
  ['pm', 'pm', '±'],
  ['in', 'in', '∈'],
  ['subset', 'subset', '⊂'],
  ['cup', 'cup', '∪'],
  ['cap', 'cap', '∩'],
  ['forall', 'forall', '∀'],
  ['exists', 'exists', '∃'],
  ['rightarrow', 'rightarrow', '→'],
  ['Rightarrow', 'Rightarrow', '⇒'],
  ['leftrightarrow', 'leftrightarrow', '↔'],
  ['mapsto', 'mapsto', '↦'],
  ['to', 'to', '→'],
  ['alpha', 'alpha', 'α'], ['beta', 'beta', 'β'], ['gamma', 'gamma', 'γ'], ['delta', 'delta', 'δ'],
  ['epsilon', 'epsilon', 'ε'], ['varepsilon', 'varepsilon', 'ε'], ['zeta', 'zeta', 'ζ'], ['eta', 'eta', 'η'],
  ['theta', 'theta', 'θ'], ['kappa', 'kappa', 'κ'], ['lambda', 'lambda', 'λ'], ['mu', 'mu', 'μ'],
  ['nu', 'nu', 'ν'], ['xi', 'xi', 'ξ'], ['pi', 'pi', 'π'], ['rho', 'rho', 'ρ'], ['sigma', 'sigma', 'σ'],
  ['tau', 'tau', 'τ'], ['phi', 'phi', 'φ'], ['varphi', 'varphi', 'φ'], ['chi', 'chi', 'χ'], ['psi', 'psi', 'ψ'],
  ['omega', 'omega', 'ω'], ['Gamma', 'Gamma', 'Γ'], ['Delta', 'Delta', 'Δ'], ['Theta', 'Theta', 'Θ'],
  ['Lambda', 'Lambda', 'Λ'], ['Sigma', 'Sigma', 'Σ'], ['Phi', 'Phi', 'Φ'], ['Psi', 'Psi', 'Ψ'], ['Omega', 'Omega', 'Ω'],
  ['mathbb', 'mathbb{${1:R}}', 'Blackboard bold'],
  ['mathcal', 'mathcal{${1}}', 'Calligraphic'],
  ['mathbf', 'mathbf{${1}}', 'Bold math'],
  ['mathrm', 'mathrm{${1}}', 'Roman math'],
  ['text', 'text{${1}}', 'Text in math'],
  ['left', 'left( ${1} \\right)', 'Scaled delimiters'],
  ['hat', 'hat{${1}}', ''], ['bar', 'bar{${1}}', ''], ['vec', 'vec{${1}}', ''], ['dot', 'dot{${1}}', ''],
  ['overline', 'overline{${1}}', ''], ['tilde', 'tilde{${1}}', ''],
  ['quad', 'quad', ''], ['qquad', 'qquad', ''],
  ['toprule', 'toprule', 'booktabs'], ['midrule', 'midrule', 'booktabs'], ['bottomrule', 'bottomrule', 'booktabs'],
  ['hline', 'hline', ''], ['multicolumn', 'multicolumn{${1:2}}{${2:c}}{${3}}', ''],
  ['addplot', 'addplot {${1:x^2}};', 'pgfplots'],
  ['addplot table', 'addplot table[x=${1:x}, y=${2:y}, col sep=comma] {${3:data.csv}};', 'pgfplots from file'],
  ['addlegendentry', 'addlegendentry{${1}}', 'pgfplots'],
  ['draw', 'draw (${1:0,0}) -- (${2:1,1});', 'TikZ'],
  ['node', 'node[${1}] (${2:name}) at (${3:0,0}) {${4}};', 'TikZ'],
  ['graphicspath', 'graphicspath{{${1:images/}}}', ''],
  ['appendix', 'appendix', ''],
  ['frametitle', 'frametitle{${1}}', 'Beamer'],
  ['pause', 'pause', 'Beamer'],
];

const PACKAGES = [
  'amsmath', 'amssymb', 'amsthm', 'mathtools', 'graphicx', 'xcolor', 'hyperref', 'cleveref', 'geometry', 'booktabs',
  'tabularx', 'longtable', 'multirow', 'array', 'caption', 'subcaption', 'float', 'wrapfig', 'tikz', 'pgfplots',
  'pgfplotstable', 'siunitx', 'biblatex', 'natbib', 'csquotes', 'babel', 'polyglossia', 'fontspec', 'inputenc',
  'fontenc', 'lmodern', 'microtype', 'listings', 'minted', 'algorithm', 'algpseudocode', 'enumitem', 'fancyhdr',
  'titlesec', 'setspace', 'parskip', 'lipsum', 'blindtext', 'todonotes', 'url', 'xurl', 'pdfpages', 'appendix',
  'glossaries', 'makeidx', 'nomencl', 'acronym', 'physics', 'chemfig', 'mhchem', 'circuitikz', 'forest', 'svg',
  'tcolorbox', 'mdframed', 'framed', 'multicol', 'rotating', 'pdflscape', 'threeparttable', 'dcolumn', 'colortbl',
  'xspace', 'ifthen', 'etoolbox', 'calc', 'datetime2', 'hyphenat', 'ragged2e', 'footmisc', 'epigraph', 'lettrine',
];

const CLASSES = ['article', 'report', 'book', 'beamer', 'letter', 'memoir', 'scrartcl', 'scrreprt', 'scrbook', 'standalone', 'moderncv', 'IEEEtran', 'llncs', 'acmart', 'amsart', 'revtex4-2'];

const REF_CMDS = /^(ref|eqref|cref|Cref|autoref|pageref|nameref|vref|Vref|labelcref|cpageref|Cpageref|subref)$/;
const CITE_CMDS = /^(cite|citep|citet|citealp|citealt|citeauthor|citeyear|autocite|parencite|textcite|footcite|smartcite|supercite|fullcite|nocite|Autocite|Textcite|Parencite|Cite|citetitle|Citeauthor|Citet|Citep|footfullcite)$/;
const IMG_EXT = /\.(png|jpe?g|pdf|eps|gif|bmp|svg|webp|tiff?)$/i;

export function registerLatex(monaco, getSymbols) {
  monaco.languages.register({ id: 'latex', extensions: ['.tex', '.sty', '.cls', '.ltx', '.dtx', '.tikz', '.pgf'] });
  monaco.languages.register({ id: 'bibtex', extensions: ['.bib'] });

  monaco.languages.setLanguageConfiguration('latex', {
    comments: { lineComment: '%' },
    brackets: [['{', '}'], ['[', ']'], ['(', ')']],
    autoClosingPairs: [
      { open: '{', close: '}' },
      { open: '[', close: ']' },
      { open: '(', close: ')' },
      { open: '$', close: '$', notIn: ['comment'] },
    ],
    surroundingPairs: [
      { open: '{', close: '}' },
      { open: '[', close: ']' },
      { open: '(', close: ')' },
      { open: '$', close: '$' },
    ],
    wordPattern: /(-?\d*\.\d\w*)|([^`~!@#%^&*()\-=+[{\]}\\|;:'",.<>/?\s$]+)/g,
    folding: { markers: { start: /^\s*\\begin\{/, end: /^\s*\\end\{/ } },
    onEnterRules: [
      {
        beforeText: /^\s*\\begin\{(?!document\})[^}]+\}.*$/,
        action: { indentAction: monaco.languages.IndentAction.Indent },
      },
    ],
  });

  monaco.languages.setMonarchTokensProvider('latex', {
    defaultToken: '',
    tokenizer: {
      root: [
        [/%.*$/, 'comment'],
        [new RegExp(`(\\\\begin)(\\{)(${VERB_ENVS})(\\*?)(\\})`), ['keyword', 'delimiter.curly', 'type', 'type', { token: 'delimiter.curly', next: '@verbatim' }]],
        [new RegExp(`(\\\\begin)(\\{)((?:${MATH_ENVS})\\*?)(\\})`), ['keyword', 'delimiter.curly', 'type', { token: 'delimiter.curly', next: '@mathEnv' }]],
        [/(\\(?:begin|end))(\{)([^}]*)(\})/, ['keyword', 'delimiter.curly', 'type', 'delimiter.curly']],
        [/\\(?:part|chapter|section|subsection|subsubsection|paragraph|subparagraph|frametitle)\*?(?=[{[\s])/, 'keyword.section'],
        [/\\(?:label|ref|eqref|cref|Cref|autoref|pageref|nameref|subref)\b/, 'keyword.ref'],
        [/\\(?:[a-zA-Z]*cite[a-zA-Z]*|nocite)\b/, 'keyword.ref'],
        [/\\labstale(?:\[[^\]]*\])?(?:\{[^{}]*\})?/, 'keyword.stale'],
        [/\\(?:usepackage|RequirePackage|documentclass|input|include|includegraphics|addbibresource|bibliography|bibliographystyle|graphicspath)\b/, 'keyword.include'],
        [/\\verb\*?([^a-zA-Z\s]).*?\1/, 'string'],
        [/\\[a-zA-Z@]+\*?/, 'keyword'],
        [/\\[^a-zA-Z]/, 'keyword.escape'],
        [/\$\$/, { token: 'string.math', next: '@mathDisplay' }],
        [/\$/, { token: 'string.math', next: '@mathInline' }],
        [/\\\[/, { token: 'string.math', next: '@mathBracket' }],
        [/\\\(/, { token: 'string.math', next: '@mathParen' }],
        [/[{}]/, 'delimiter.curly'],
        [/[[\]]/, 'delimiter.square'],
        [/[&~]/, 'delimiter'],
        [/[^\\%${}[\]&~]+/, ''],
      ],
      mathInline: [[/\$/, { token: 'string.math', next: '@pop' }], { include: '@mathCommon' }],
      mathDisplay: [[/\$\$/, { token: 'string.math', next: '@pop' }], { include: '@mathCommon' }],
      mathBracket: [[/\\\]/, { token: 'string.math', next: '@pop' }], { include: '@mathCommon' }],
      mathParen: [[/\\\)/, { token: 'string.math', next: '@pop' }], { include: '@mathCommon' }],
      mathEnv: [
        [new RegExp(`(\\\\end)(\\{)((?:${MATH_ENVS})\\*?)(\\})`), ['keyword', 'delimiter.curly', 'type', { token: 'delimiter.curly', next: '@pop' }]],
        [/(\\(?:begin|end))(\{)([^}]*)(\})/, ['keyword', 'delimiter.curly', 'type', 'delimiter.curly']],
        [/\\(?:label|ref|eqref)\b/, 'keyword.ref'],
        { include: '@mathCommon' },
      ],
      mathCommon: [
        [/%.*$/, 'comment'],
        [/\\[a-zA-Z]+/, 'keyword.math'],
        [/\\[^a-zA-Z]/, 'keyword.math'],
        [/[{}]/, 'delimiter.curly.math'],
        [/[^\\%${}]+/, 'string.math'],
        [/./, 'string.math'],
      ],
      verbatim: [
        [new RegExp(`(\\\\end)(\\{)(${VERB_ENVS})(\\*?)(\\})`), ['keyword', 'delimiter.curly', 'type', 'type', { token: 'delimiter.curly', next: '@pop' }]],
        [/.+/, 'string.verbatim'],
      ],
    },
  });

  monaco.languages.setLanguageConfiguration('bibtex', {
    comments: { lineComment: '%' },
    brackets: [['{', '}'], ['(', ')']],
    autoClosingPairs: [{ open: '{', close: '}' }, { open: '"', close: '"' }],
  });
  monaco.languages.setMonarchTokensProvider('bibtex', {
    tokenizer: {
      root: [
        [/%.*$/, 'comment'],
        [/(@\w+)(\s*\{\s*)([^,\s]+)(,)/, ['keyword', 'delimiter.curly', 'type', 'delimiter']],
        [/@\w+/, 'keyword'],
        [/\b([a-zA-Z_-]+)(\s*=)/, ['attribute.name', 'delimiter']],
        [/"[^"]*"/, 'string'],
        [/\d+/, 'number'],
        [/[{}]/, 'delimiter.curly'],
      ],
    },
  });

  // ----- completions
  const kinds = monaco.languages.CompletionItemKind;
  const snippetRule = monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet;

  monaco.languages.registerCompletionItemProvider('latex', {
    triggerCharacters: ['\\', '{', ',', '/'],
    provideCompletionItems(model, position) {
      const line = model.getLineContent(position.lineNumber);
      const before = line.slice(0, position.column - 1);
      const after = line.slice(position.column - 1);
      const sym = getSymbols();

      // pgfplots: \addplot table {file}
      let m = /\btable\s*(?:\[[^\]]*\])?\s*\{([^}]*)$/.exec(before);
      if (m) return fileItems(m[1], (f) => /\.(csv|dat|txt|tsv)$/i.test(f), (f) => f);

      m = /\\([a-zA-Z]+)\*?(?:\[[^\]]*\])*\{([^{}]*)$/.exec(before);
      if (m) {
        const cmd = m[1];
        const arg = m[2];
        const typed = arg.slice(arg.lastIndexOf(',') + 1).trimStart();
        const range = new monaco.Range(position.lineNumber, position.column - typed.length, position.lineNumber, position.column);
        const closeAfter = after.startsWith('}');

        if (cmd === 'begin') {
          const endRange = closeAfter
            ? new monaco.Range(position.lineNumber, range.startColumn, position.lineNumber, position.column + 1)
            : range;
          return {
            suggestions: ENVIRONMENTS.map(([name, snip]) => {
              // Snippet already contains \begin{name}; we are inside "\begin{", so drop that prefix.
              const body = snip.replace(/^\\begin\{[^}]*\}/, '');
              return {
                label: name,
                kind: kinds.Module,
                detail: 'environment',
                insertText: name.replace(/\*/g, '\\*') + '}' + body,
                insertTextRules: snippetRule,
                range: endRange,
              };
            }),
          };
        }
        if (cmd === 'end') {
          return { suggestions: ENVIRONMENTS.map(([name]) => ({ label: name, kind: kinds.Module, insertText: name, range })) };
        }
        if (REF_CMDS.test(cmd)) {
          return {
            suggestions: sym.labels.map((l) => ({
              label: l.label,
              kind: kinds.Reference,
              detail: `${l.file}:${l.line}`,
              insertText: l.label,
              range,
            })),
          };
        }
        if (CITE_CMDS.test(cmd)) {
          return {
            suggestions: sym.cites.map((c) => ({
              label: { label: c.key, description: c.year },
              kind: kinds.Value,
              detail: c.title,
              documentation: [c.author, c.year, c.file].filter(Boolean).join(' · '),
              filterText: `${c.key} ${c.title} ${c.author}`,
              insertText: c.key,
              range,
            })),
          };
        }
        if (cmd === 'includegraphics') return fileItems(typed, (f) => IMG_EXT.test(f), (f) => f, range);
        if (cmd === 'input' || cmd === 'include' || cmd === 'subfile' || cmd === 'includeonly')
          return fileItems(typed, (f) => /\.tex$/i.test(f), (f) => (cmd === 'include' ? f.replace(/\.tex$/i, '') : f), range);
        if (cmd === 'addbibresource') return fileItems(typed, (f) => /\.bib$/i.test(f), (f) => f, range);
        if (cmd === 'bibliography') return fileItems(typed, (f) => /\.bib$/i.test(f), (f) => f.replace(/\.bib$/i, ''), range);
        if (cmd === 'usepackage' || cmd === 'RequirePackage')
          return { suggestions: PACKAGES.map((p) => ({ label: p, kind: kinds.Module, insertText: p, range })) };
        if (cmd === 'documentclass')
          return { suggestions: CLASSES.map((p) => ({ label: p, kind: kinds.Class, insertText: p, range })) };
        if (cmd === 'bibliographystyle')
          return { suggestions: ['plain', 'plainnat', 'unsrt', 'unsrtnat', 'alpha', 'abbrv', 'abbrvnat', 'ieeetr', 'apalike', 'IEEEtran'].map((p) => ({ label: p, kind: kinds.Enum, insertText: p, range })) };
        return { suggestions: [] };

        function fileItems(typedText, filter, map, rng = range) {
          return {
            suggestions: sym.files.filter(filter).map((f) => ({
              label: map(f),
              kind: kinds.File,
              insertText: map(f),
              range: rng,
            })),
          };
        }
      }

      m = /\\([a-zA-Z@]*)$/.exec(before);
      if (m) {
        const range = new monaco.Range(position.lineNumber, position.column - m[1].length, position.lineNumber, position.column);
        const items = COMMANDS.map(([name, snip, detail], i) => ({
          label: '\\' + name,
          kind: name === 'begin' ? kinds.Snippet : kinds.Function,
          detail,
          insertText: snip,
          insertTextRules: snippetRule,
          filterText: name,
          sortText: String(i).padStart(4, '0'),
          range,
        }));
        // Commands defined in the project
        for (const c of sym.commands) {
          const args = Array.from({ length: c.args }, (_, i) => `{\${${i + 1}}}`).join('');
          items.push({ label: '\\' + c.name, kind: kinds.Variable, detail: 'defined in project', insertText: c.name + args, insertTextRules: snippetRule, filterText: c.name, range });
        }
        // Environment shortcuts: typing \fig... offers the whole figure environment
        for (const [name, snip] of ENVIRONMENTS) {
          items.push({
            label: `\\begin{${name}}`,
            kind: kinds.Snippet,
            detail: 'environment',
            insertText: snip.slice(1),
            insertTextRules: snippetRule,
            filterText: 'begin' + name,
            sortText: 'z' + name,
            range,
          });
        }
        return { suggestions: items };
      }
      return { suggestions: [] };
    },
  });

  // ----- hover for citations and references
  monaco.languages.registerHoverProvider('latex', {
    provideHover(model, position) {
      const line = model.getLineContent(position.lineNumber);
      // a value or reference frozen when its Folio Lab result was removed
      for (const s of line.matchAll(/\\labstale(?:\[([^\]]*)\])?\{([^{}]*)\}/g)) {
        if (position.column < s.index + 1 || position.column > s.index + s[0].length + 1) continue;
        return {
          range: new monaco.Range(position.lineNumber, s.index + 1, position.lineNumber, s.index + s[0].length + 1),
          contents: [
            { value: `⚠ **No longer backed by a result**${s[1] ? ` (was *${s[1]}*)` : ''}` },
            { value: `The text \`${s[2]}\` stays as it was printed and is marked with † in the PDF. It no longer updates; replace it with your own wording or a new value when you are ready.` },
          ],
        };
      }
      const re = /\\([a-zA-Z]+)\*?(?:\[[^\]]*\])*\{([^}]*)\}/g;
      let m;
      while ((m = re.exec(line))) {
        const start = m.index + m[0].indexOf('{') + 2;
        const end = m.index + m[0].length;
        if (position.column < start || position.column > end) continue;
        const col = position.column - start;
        let acc = 0;
        let key = null;
        for (const part of m[2].split(',')) {
          if (col >= acc && col <= acc + part.length) key = part.trim();
          acc += part.length + 1;
        }
        if (!key) return null;
        const sym = getSymbols();
        if (CITE_CMDS.test(m[1])) {
          const c = sym.cites.find((x) => x.key === key);
          if (!c) return { contents: [{ value: `⚠ No bibliography entry **${key}** found in the project's .bib files.` }] };
          return { contents: [{ value: `**${c.title || key}**` }, { value: [c.author, c.year].filter(Boolean).join(', ') + `  \n_${c.type} · ${c.file}_` }] };
        }
        if (REF_CMDS.test(m[1])) {
          const l = sym.labels.find((x) => x.label === key);
          return { contents: [{ value: l ? `Label **${key}** — ${l.file}, line ${l.line}` : `⚠ Label **${key}** is not defined.` }] };
        }
      }
      return null;
    },
  });

  // ----- themes
  const rules = (dark) => [
    { token: 'comment', foreground: dark ? '7f848e' : '8a8f98', fontStyle: 'italic' },
    { token: 'keyword', foreground: dark ? '82aaff' : '2a4fc2' },
    { token: 'keyword.escape', foreground: dark ? '82aaff' : '2a4fc2' },
    { token: 'keyword.section', foreground: dark ? 'e5a8ff' : '8b2fb8', fontStyle: 'bold' },
    { token: 'keyword.ref', foreground: dark ? '5fd4c4' : '0f7d72' },
    { token: 'keyword.stale', foreground: dark ? 'ffb454' : 'b45309', fontStyle: 'italic underline' },
    { token: 'keyword.include', foreground: dark ? 'f0a35e' : 'b4570b' },
    { token: 'keyword.math', foreground: dark ? 'b5d97a' : '43761a' },
    { token: 'type', foreground: dark ? 'f7c26b' : 'a35d00' },
    { token: 'string.math', foreground: dark ? 'a7d38a' : '2f7a2f' },
    { token: 'delimiter.curly.math', foreground: dark ? 'a7d38a' : '2f7a2f' },
    { token: 'string.verbatim', foreground: dark ? 'c8c8c8' : '555555' },
    { token: 'string', foreground: dark ? 'c3e88d' : '2f7a2f' },
    { token: 'delimiter.curly', foreground: dark ? '9aa0aa' : '6b7280' },
    { token: 'delimiter.square', foreground: dark ? '9aa0aa' : '6b7280' },
    { token: 'delimiter', foreground: dark ? 'ff9e64' : 'c2410c' },
    { token: 'attribute.name', foreground: dark ? 'f7c26b' : 'a35d00' },
    { token: 'number', foreground: dark ? 'f78c6c' : 'b45309' },
  ];
  monaco.editor.defineTheme('folio-light', {
    base: 'vs',
    inherit: true,
    rules: rules(false),
    colors: { 'editor.background': '#ffffff', 'editorLineNumber.foreground': '#a8abb2', 'editor.lineHighlightBackground': '#f5f6f8' },
  });
  monaco.editor.defineTheme('folio-dark', {
    base: 'vs-dark',
    inherit: true,
    rules: rules(true),
    colors: { 'editor.background': '#1f2024', 'editorLineNumber.foreground': '#5c6068', 'editor.lineHighlightBackground': '#26282d' },
  });
}

export function languageFor(path) {
  const ext = (path.split('.').pop() || '').toLowerCase();
  return (
    {
      tex: 'latex', sty: 'latex', cls: 'latex', ltx: 'latex', dtx: 'latex', tikz: 'latex', pgf: 'latex', bbl: 'latex', clo: 'latex', def: 'latex',
      bib: 'bibtex', md: 'markdown', json: 'json', lua: 'lua', py: 'python', r: 'r', js: 'javascript', ts: 'typescript',
      yaml: 'yaml', yml: 'yaml', xml: 'xml', html: 'html', css: 'css', sh: 'shell', bat: 'bat', ps1: 'powershell',
      m: 'plaintext', jl: 'julia', cpp: 'cpp', c: 'c', h: 'cpp', java: 'java',
    }[ext] || 'plaintext'
  );
}

/** Extract an outline (sections) from LaTeX source. */
export function outline(text) {
  const levels = { part: 0, chapter: 0, section: 1, subsection: 2, subsubsection: 3, paragraph: 4, frametitle: 2 };
  const out = [];
  const lines = text.split('\n');
  const re = /^[^%]*?\\(part|chapter|section|subsection|subsubsection|paragraph|frametitle)\*?\s*(?:\[[^\]]*\])?\s*\{(.*)/;
  lines.forEach((l, i) => {
    const m = re.exec(l);
    if (!m) return;
    let depth = 0;
    let title = '';
    for (const ch of m[2]) {
      if (ch === '{') depth++;
      if (ch === '}') {
        if (depth === 0) break;
        depth--;
      }
      title += ch;
    }
    title = title.replace(/\\[a-zA-Z]+\*?\s*/g, '').replace(/[{}$]/g, '').trim();
    out.push({ level: levels[m[1]], title: title || '(untitled)', line: i + 1 });
  });
  return out;
}
