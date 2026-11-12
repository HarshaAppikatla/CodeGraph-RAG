import React, { useEffect, useState } from 'react';
import mermaid from 'mermaid';
import DOMPurify from 'dompurify';
import { Copy, Check, Download, Compass, Image as ImageIcon } from 'lucide-react';

mermaid.initialize({
  startOnLoad: false,
  suppressErrorRendering: true,
  theme: 'dark',
  htmlLabels: true,
  securityLevel: 'strict',
  flowchart: {
    htmlLabels: true,
    useMaxWidth: true,
    curve: 'basis',
    diagramPadding: 16,
    nodeSpacing: 45,
    rankSpacing: 60
  },
  sequence: {
    useMaxWidth: true
  },
  themeVariables: {
    darkMode: true,
    background: '#020617',
    mainBkg: '#020617',
    primaryColor: '#0f172a',
    primaryTextColor: '#f8fafc',
    primaryBorderColor: '#0284c7',
    lineColor: '#38bdf8',
    secondaryColor: '#1e1b4b',
    tertiaryColor: '#022c22',
    clusterBkg: '#0a0f1d',
    clusterBorder: '#334155',
    titleColor: '#38bdf8',
    edgeLabelBackground: '#020617',
    fontFamily: 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    fontSize: '13px'
  }
});

// Helper to sanitize and auto-theme mermaid syntax
const preprocessChart = (raw) => {
  if (!raw) return '';
  let clean = raw.trim();

  // 0. Remove markdown code fences if passed
  clean = clean.replace(/^```(?:mermaid)?\s*/i, '').replace(/\s*```$/, '').trim();

  // Strip dangerous script tags, inline event handlers, and javascript schemes to prevent XSS
  clean = clean.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '');
  clean = clean.replace(/on\w+\s*=\s*["'][^"']*["']/gi, '');
  clean = clean.replace(/javascript:\s*/gi, '');

  // 1. Normalize linebreaks inside quoted strings to <br/> so text never spills out
  clean = clean.replace(/"([^"]*)"/g, (match, inner) => {
    const replaced = inner.replace(/\\n/g, '<br/>').replace(/\r?\n/g, '<br/>');
    return `"${replaced}"`;
  });

  // 2. Protect existing quoted strings and auto-quote unquoted labels containing parentheses or special characters
  const lines = clean.split(/\r?\n/);
  const processed = lines.map(line => {
    let l = line;
    const trimmed = l.trim();
    if (
      trimmed.startsWith('%%') ||
      trimmed.startsWith('classDef') ||
      trimmed.startsWith('class ') ||
      trimmed.startsWith('style ') ||
      trimmed.startsWith('linkStyle') ||
      trimmed.startsWith('subgraph') ||
      trimmed === 'end'
    ) {
      return l;
    }

    // Protect all existing quoted strings with temporary placeholders
    const placeholders = [];
    l = l.replace(/"([^"]*)"/g, (match) => {
      const idx = placeholders.length;
      placeholders.push(match);
      return `__MERMAID_QUOTE_PH_${idx}__`;
    });

    // Square brackets: ID[label] (exclude [[subroutine]], [(cylinder)], [|pipe|])
    l = l.replace(/(\b[A-Za-z0-9_-]+)\s*\[(?![[(|/])([^\]\r\n]+)\]/g, (match, id, label) => {
      if (label.includes('__MERMAID_QUOTE_PH_')) return match;
      if (/[()<>+&/:;,{}]/.test(label)) {
        return `${id}["${label.trim()}"]`;
      }
      return match;
    });

    // Stadium: ID([label])
    l = l.replace(/(\b[A-Za-z0-9_-]+)\s*\(\[([^\]\r\n]+)\]\)/g, (match, id, label) => {
      if (label.includes('__MERMAID_QUOTE_PH_')) return match;
      if (/[()<>+&/:;,{}]/.test(label)) {
        return `${id}(["${label.trim()}"])`;
      }
      return match;
    });

    // Cylinder / Database: ID[(label)]
    l = l.replace(/(\b[A-Za-z0-9_-]+)\s*\[\(([^)\r\n]+)\)\]/g, (match, id, label) => {
      if (label.includes('__MERMAID_QUOTE_PH_')) return match;
      if (/[()<>+&/:;,{}]/.test(label)) {
        return `${id}[("${label.trim()}")]`;
      }
      return match;
    });

    // Rhombus / Diamond: ID{label} (exclude {{hexagon}})
    l = l.replace(/(\b[A-Za-z0-9_-]+)\s*\{(?![{])([^}\r\n]+)\}/g, (match, id, label) => {
      if (label.includes('__MERMAID_QUOTE_PH_')) return match;
      if (/[()<>+&/:;,]/.test(label)) {
        return `${id}{"${label.trim()}"}`;
      }
      return match;
    });

    // Rounded: ID(label) (exclude ([stadium]), ((circle)))
    l = l.replace(/(\b[A-Za-z0-9_-]+)\s*\((?![[(])([^)\r\n]+)\)/g, (match, id, label) => {
      if (label.includes('__MERMAID_QUOTE_PH_')) return match;
      if (/[()<>+&/:;,{}[\]]/.test(label)) {
        return `${id}("${label.trim()}")`;
      }
      return match;
    });

    // Restore quoted strings
    l = l.replace(/__MERMAID_QUOTE_PH_(\d+)__/g, (match, idx) => {
      return placeholders[parseInt(idx, 10)] || match;
    });

    return l;
  });
  clean = processed.join('\n');

  // 3. If no custom classes or styles are provided, inject rich architectural theme classes
  if (!clean.includes('classDef ') && (clean.startsWith('flowchart') || clean.startsWith('graph'))) {
    const subgraphRegex = /subgraph\s+([A-Za-z0-9_]+)[^\n]*\r?\n([\s\S]*?)end/g;
    let match;
    const layerClasses = [];
    const styles = [];

    const palettes = [
      { name: 'client', nodeFill: '#0c4a6e', nodeStroke: '#38bdf8', subFill: '#082f49', subStroke: '#0284c7', subColor: '#38bdf8', text: '#f0f9ff' },
      { name: 'interface', nodeFill: '#312e81', nodeStroke: '#818cf8', subFill: '#1e1b4b', subStroke: '#6366f1', subColor: '#818cf8', text: '#e0e7ff' },
      { name: 'backend', nodeFill: '#064e3b', nodeStroke: '#34d399', subFill: '#022c22', subStroke: '#059669', subColor: '#34d399', text: '#ecfdf5' },
      { name: 'storage', nodeFill: '#78350f', nodeStroke: '#fbbf24', subFill: '#451a03', subStroke: '#d97706', subColor: '#fbbf24', text: '#fffbeb' },
      { name: 'accent', nodeFill: '#4c1d95', nodeStroke: '#c084fc', subFill: '#2e1065', subStroke: '#9333ea', subColor: '#c084fc', text: '#faf5ff' },
    ];

    let paletteIdx = 0;
    while ((match = subgraphRegex.exec(clean)) !== null) {
      const subName = match[1];
      const subBody = match[2];

      let chosenPalette = palettes[paletteIdx % palettes.length];
      const lower = subName.toLowerCase();
      if (lower.includes('client') || lower.includes('ui') || lower.includes('front')) {
        chosenPalette = palettes[0];
      } else if (lower.includes('interface') || lower.includes('api') || lower.includes('protocol') || lower.includes('gateway')) {
        chosenPalette = palettes[1];
      } else if (lower.includes('service') || lower.includes('backend') || lower.includes('engine') || lower.includes('core')) {
        chosenPalette = palettes[2];
      } else if (lower.includes('store') || lower.includes('storage') || lower.includes('data') || lower.includes('persist') || lower.includes('graph')) {
        chosenPalette = palettes[3];
      } else {
        paletteIdx++;
      }

      const nodeRegex = /^\s*([A-Za-z0-9_]+)\s*(\[|\(|\{\|>)/gm;
      let nodeMatch;
      const nodeIds = [];
      while ((nodeMatch = nodeRegex.exec(subBody)) !== null) {
        if (nodeMatch[1] && nodeMatch[1] !== 'subgraph') {
          nodeIds.push(nodeMatch[1]);
        }
      }

      const className = `theme_${subName}`;
      layerClasses.push(`    classDef ${className} fill:${chosenPalette.nodeFill},stroke:${chosenPalette.nodeStroke},stroke-width:2px,color:${chosenPalette.text};`);
      if (nodeIds.length > 0) {
        layerClasses.push(`    class ${nodeIds.join(',')} ${className};`);
      }
      styles.push(`    style ${subName} fill:${chosenPalette.subFill},stroke:${chosenPalette.subStroke},stroke-width:2px,stroke-dasharray: 4 4,color:${chosenPalette.subColor};`);
    }

    if (layerClasses.length > 0) {
      clean += '\n\n    %% Architectural Layer Theming\n' + layerClasses.join('\n') + '\n' + styles.join('\n');
    }
  }

  return clean;
};

// Module-level global cache for rendered SVGs so they render once and NEVER re-render or flash
const svgRenderCache = new Map();

export const MermaidViewer = React.memo(({ chart }) => {
  const cleanChart = chart ? preprocessChart(chart) : '';
  const [svg, setSvg] = useState(() => (cleanChart ? svgRenderCache.get(cleanChart) || '' : ''));
  const [prevChart, setPrevChart] = useState(cleanChart);
  if (cleanChart !== prevChart) {
    setPrevChart(cleanChart);
    if (svgRenderCache.has(cleanChart)) {
      setSvg(svgRenderCache.get(cleanChart));
    }
  }

  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!cleanChart) return;
    if (svgRenderCache.has(cleanChart)) return;

    let isMounted = true;
    const renderChart = async () => {
      try {
        const id = `mermaid-${Math.random().toString(36).substring(2, 9)}`;
        const { svg: renderedSvg } = await mermaid.render(id, cleanChart);
        svgRenderCache.set(cleanChart, renderedSvg);
        if (isMounted) {
          setSvg(renderedSvg);
          setError(null);
        }
      } catch (err) {
        // Clean up any stray error elements injected into document.body by Mermaid
        try {
          document.querySelectorAll('[id^="dmermaid"], [id^="mermaid-"]').forEach(el => {
            if (el.tagName !== 'svg') el.remove();
          });
        } catch {}

        // Secondary fallback pass: aggressive sanitation if first pass threw a syntax notice
        try {
          const aggressiveClean = cleanChart
            .replace(/\[([^\]"]*)\(([^)]*)\)([^\]"]*)\]/g, '["$1 - $2$3"]')
            .replace(/\(([^)"]*)\[([^\]]*)\]([^)"]*)\)/g, '("$1 - $2$3")');
          const fallbackId = `mermaid-fb-${Math.random().toString(36).substring(2, 9)}`;
          const { svg: fbSvg } = await mermaid.render(fallbackId, aggressiveClean);
          svgRenderCache.set(cleanChart, fbSvg);
          if (isMounted) {
            setSvg(fbSvg);
            setError(null);
            return;
          }
        } catch {}

        console.warn('Mermaid rendering notice:', err);
        if (isMounted) {
          setError(err?.message || 'Diagram syntax notice');
        }
      }
    };

    renderChart();
    return () => {
      isMounted = false;
    };
  }, [cleanChart]);

  const handleCopyCode = async () => {
    try {
      await navigator.clipboard.writeText(chart.trim());
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.warn('Failed to copy diagram code:', err);
    }
  };

  const handleDownloadSvg = () => {
    if (!svg) return;
    const blob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `architecture-diagram-${Date.now()}.svg`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleDownloadPng = () => {
    if (!svg) return;
    try {
      // 1. Repair unclosed void HTML tags from Mermaid HTML labels before XML DOM parsing
      // This eliminates fatal XML parsererror ("Unexpected closing tag: </p> != <br>") that truncated nodes
      const wellFormedSvg = svg
        .replace(/<br>/gi, '<br/>')
        .replace(/<hr>/gi, '<hr/>')
        .replace(/<img\b([^>]*)(?<!\/)>/gi, '<img$1/>')
        .replace(/<input\b([^>]*)(?<!\/)>/gi, '<input$1/>');

      const parser = new DOMParser();
      const doc = parser.parseFromString(wellFormedSvg, 'image/svg+xml');
      const svgEl = doc.querySelector('svg');
      if (!svgEl) {
        handleDownloadSvg();
        return;
      }

      // Determine true diagram bounds from viewBox or attributes
      const rawWidth = svgEl.getAttribute('width');
      const rawHeight = svgEl.getAttribute('height');
      const viewBox = svgEl.getAttribute('viewBox');

      let width = 0;
      let height = 0;

      if (viewBox) {
        const parts = viewBox.trim().split(/[\s,]+/).map(Number);
        if (parts.length === 4 && parts[2] > 0 && parts[3] > 0) {
          width = parts[2];
          height = parts[3];
        }
      }

      if (!width || !height) {
        if (rawWidth && !rawWidth.includes('%')) width = parseFloat(rawWidth);
        if (rawHeight && !rawHeight.includes('%')) height = parseFloat(rawHeight);
      }

      width = width || 1200;
      height = height || 800;

      // Explicitly set width & height attributes on the SVG clone so it renders at full resolution
      svgEl.setAttribute('width', String(width));
      svgEl.setAttribute('height', String(height));

      // Strip any external @import rules in <style> to prevent CORS canvas tainting
      const styles = svgEl.querySelectorAll('style');
      styles.forEach(s => {
        if (s.textContent) {
          s.textContent = s.textContent.replace(/@import\s+[^;]+;/gi, '');
        }
      });

      // HTML entity decoder helper
      const decodeHtmlEntities = (str) => {
        return str
          .replace(/&amp;/g, '&')
          .replace(/&lt;/g, '<')
          .replace(/&gt;/g, '>')
          .replace(/&quot;/g, '"')
          .replace(/&#39;/g, "'");
      };

      // Smart line breaker so multi-line text stays neatly inside node boundaries
      const splitIntoFittingLines = (rawLines, boxWidth, fontSize) => {
        const approxCharWidth = fontSize * 0.58;
        const maxChars = Math.max(12, Math.floor((boxWidth - 10) / approxCharWidth));
        const finalLines = [];

        for (const line of rawLines) {
          const decoded = decodeHtmlEntities(line).trim();
          if (!decoded) continue;

          if (decoded.length <= maxChars) {
            finalLines.push(decoded);
            continue;
          }

          // Break gracefully on spaces, commas, or slash separators
          const tokens = decoded.split(/(?<=[,\s]|\s\/\s)/g);
          let current = '';
          for (const token of tokens) {
            if (!current) {
              current = token;
            } else if ((current + token).length <= maxChars) {
              current += token;
            } else {
              if (current.trim()) finalLines.push(current.trim());
              current = token;
            }
          }
          if (current.trim()) finalLines.push(current.trim());
        }

        return finalLines;
      };

      // Convert all foreignObject elements to native SVG <text>/<tspan> elements
      // Eliminates the Chromium 'tainted canvas' SecurityError while guaranteeing 100% of node boxes, fills, and labels
      const foreignObjects = Array.from(svgEl.querySelectorAll('foreignObject'));
      foreignObjects.forEach(fo => {
        const x = parseFloat(fo.getAttribute('x') || 0);
        const y = parseFloat(fo.getAttribute('y') || 0);
        const w = parseFloat(fo.getAttribute('width') || 0);
        const h = parseFloat(fo.getAttribute('height') || 0);

        // Convert <br>, <p>, <div> to newlines to extract lines cleanly
        const clone = fo.cloneNode(true);
        clone.querySelectorAll('br').forEach(br => br.replaceWith('\n'));
        clone.querySelectorAll('p, div, li').forEach(el => el.append('\n'));
        const rawText = clone.textContent || '';
        const rawLines = rawText.split('\n').map(l => l.trim()).filter(Boolean);

        if (rawLines.length === 0) {
          fo.remove();
          return;
        }

        const isCluster = Boolean(fo.closest('.cluster-label, .cluster'));
        const isEdge = Boolean(fo.closest('.edgeLabel'));

        const baseFontSize = isCluster ? 12.5 : isEdge ? 11 : 12;
        const lines = isCluster || isEdge
          ? rawLines.map(decodeHtmlEntities)
          : splitIntoFittingLines(rawLines, w, baseFontSize);

        const textNode = doc.createElementNS('http://www.w3.org/2000/svg', 'text');
        const centerX = x + w / 2;
        textNode.setAttribute('x', String(centerX));
        textNode.setAttribute('text-anchor', 'middle');
        textNode.setAttribute('font-family', 'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif');

        const fontSize = lines.length > 3 ? 10.5 : lines.length > 2 ? 11 : baseFontSize;
        const lineHeight = fontSize * 1.35;
        const totalHeight = lines.length * lineHeight;
        const startY = y + (h - totalHeight) / 2 + fontSize * 0.88;

        textNode.setAttribute('y', String(startY));

        lines.forEach((lineText, idx) => {
          const tspan = doc.createElementNS('http://www.w3.org/2000/svg', 'tspan');
          tspan.setAttribute('x', String(centerX));
          if (idx === 0) {
            tspan.setAttribute('y', String(startY));
          } else {
            tspan.setAttribute('dy', `${lineHeight}px`);
          }

          if (isCluster) {
            tspan.setAttribute('fill', '#f1f5f9');
            tspan.setAttribute('font-size', `${fontSize}px`);
            tspan.setAttribute('font-weight', '600');
            tspan.setAttribute('letter-spacing', '0.2px');
          } else if (isEdge) {
            tspan.setAttribute('fill', '#cbd5e1');
            tspan.setAttribute('font-size', `${fontSize}px`);
            tspan.setAttribute('font-weight', '500');
          } else {
            const isSub = lineText.startsWith('(') ||
                          lineText.startsWith('[:') ||
                          lineText.startsWith('[') ||
                          lineText.includes('/') ||
                          lineText.includes('_');

            if (isSub && idx > 0) {
              tspan.setAttribute('fill', '#cbd5e1');
              tspan.setAttribute('font-size', `${Math.max(fontSize - 1.5, 9.5)}px`);
              tspan.setAttribute('font-weight', '400');
            } else {
              tspan.setAttribute('fill', '#ffffff');
              tspan.setAttribute('font-size', `${fontSize}px`);
              tspan.setAttribute('font-weight', '600');
            }
          }

          tspan.textContent = lineText;
          textNode.appendChild(tspan);
        });

        fo.parentNode?.replaceChild(textNode, fo);
      });

      if (!svgEl.getAttribute('xmlns')) {
        svgEl.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
      }

      const serializer = new XMLSerializer();
      const sanitizedSvg = serializer.serializeToString(svgEl);

      // 2x Retina scale for publication-ready project reports & Word/Docs
      const scale = 2;
      const canvas = document.createElement('canvas');
      canvas.width = width * scale;
      canvas.height = height * scale;

      const ctx = canvas.getContext('2d');
      // Dark slate background for clean contrast
      ctx.fillStyle = '#020617';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      const svgBlob = new Blob([sanitizedSvg], { type: 'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(svgBlob);
      const img = new Image();

      img.onload = () => {
        try {
          ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
          URL.revokeObjectURL(url);

          canvas.toBlob((blob) => {
            if (!blob) {
              handleDownloadSvg();
              return;
            }
            const pngUrl = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = pngUrl;
            link.download = `architecture-diagram-${Date.now()}.png`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            setTimeout(() => URL.revokeObjectURL(pngUrl), 1000);
          }, 'image/png');
        } catch (canvasErr) {
          console.warn('Canvas export tainted or blocked, falling back to SVG:', canvasErr);
          handleDownloadSvg();
        }
      };

      img.onerror = () => {
        URL.revokeObjectURL(url);
        handleDownloadSvg();
      };

      img.src = url;
    } catch (err) {
      console.warn('PNG export failed, falling back to SVG:', err);
      handleDownloadSvg();
    }
  };

  if (error) {
    return (
      <div className="my-2 p-3 bg-slate-900 border border-slate-800 rounded-xl text-slate-300 font-mono text-[11px]">
        <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-2 text-slate-400">
          <span>Mermaid Diagram Syntax</span>
          <button
            onClick={handleCopyCode}
            className="flex items-center space-x-1 text-cyan-400 hover:text-cyan-300 transition"
          >
            {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
            <span className="text-[10px]">{copied ? 'Copied' : 'Copy'}</span>
          </button>
        </div>
        <pre className="overflow-x-auto text-slate-400">{chart}</pre>
      </div>
    );
  }

  if (!svg) {
    return (
      <div className="my-2 p-4 bg-slate-900/50 border border-slate-800 rounded-xl text-center text-[11px] text-cyan-400 font-mono animate-pulse">
        Rendering architectural diagram...
      </div>
    );
  }

  return (
    <div className="my-3 rounded-2xl border border-cyan-500/30 bg-slate-950/90 shadow-xl shadow-cyan-950/30 overflow-hidden">
      {/* Action Header Bar */}
      <div className="flex items-center justify-between px-3.5 py-2 bg-slate-900/90 border-b border-slate-800/80">
        <div className="flex items-center space-x-1.5 text-cyan-400 text-[11px] font-mono font-semibold">
          <Compass className="w-3.5 h-3.5 text-cyan-400" />
          <span>Architecture Blueprint</span>
        </div>
        <div className="flex items-center space-x-2">
          {/* Copy Mermaid code */}
          <button
            onClick={handleCopyCode}
            title="Copy raw Mermaid code"
            className="flex items-center space-x-1 px-2.5 py-1 bg-slate-800/80 hover:bg-slate-700/80 text-slate-300 hover:text-cyan-300 border border-slate-700/60 rounded-lg text-[10px] font-mono transition"
          >
            {copied ? (
              <>
                <Check className="w-3 h-3 text-emerald-400" />
                <span className="text-emerald-400 font-bold">Copied!</span>
              </>
            ) : (
              <>
                <Copy className="w-3 h-3" />
                <span>Copy Code</span>
              </>
            )}
          </button>

          {/* Download high-res PNG for reports/Word/Docs */}
          <button
            onClick={handleDownloadPng}
            title="Download high-resolution PNG image (perfect for Word, Docs, Slides, and Reports)"
            className="flex items-center space-x-1 px-2.5 py-1 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 hover:text-emerald-200 border border-emerald-500/30 rounded-lg text-[10px] font-mono transition font-semibold shadow-sm"
          >
            <ImageIcon className="w-3 h-3 text-emerald-400" />
            <span>Download PNG</span>
          </button>

          {/* Download SVG vector */}
          <button
            onClick={handleDownloadSvg}
            title="Download vector SVG image"
            className="flex items-center space-x-1 px-2.5 py-1 bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 hover:text-cyan-200 border border-cyan-500/30 rounded-lg text-[10px] font-mono transition"
          >
            <Download className="w-3 h-3 text-cyan-400" />
            <span>SVG</span>
          </button>
        </div>
      </div>

      {/* Rendered Interactive SVG (sanitized via DOMPurify to eliminate XSS vectors) */}
      <div
        className="p-4 overflow-x-auto flex justify-center"
        dangerouslySetInnerHTML={{
          __html: DOMPurify.sanitize(svg, {
            USE_PROFILES: { svg: true, svgFilters: true },
            ADD_TAGS: ['foreignObject'],
            FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'form'],
            FORBID_ATTR: ['onerror', 'onload', 'onclick', 'onmouseover'],
          })
        }}
      />
    </div>
  );
});
