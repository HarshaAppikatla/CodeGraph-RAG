import React, { useEffect, useRef, useState, useCallback } from 'react';
import * as d3 from 'd3';
import { ZoomIn, ZoomOut, RefreshCw, Layers, ShieldAlert, Activity } from 'lucide-react';

export const BlastRadiusGraph = ({ graphData, onSelectNode, selectedNodeId }) => {
  const svgRef = useRef(null);
  const containerRef = useRef(null);
  const zoomBehaviorRef = useRef(null);
  const [tooltip, setTooltip] = useState(null);

  const {
    nodes = [],
    edges = [],
    name: targetName = 'Target Symbol',
    riskScore = 'N/A',
    riskLevel = 'LOW'
  } = graphData || {};

  const handleZoomIn = () => {
    if (svgRef.current && zoomBehaviorRef.current) {
      d3.select(svgRef.current).transition().duration(250).call(zoomBehaviorRef.current.scaleBy, 1.25);
    }
  };

  const handleZoomOut = () => {
    if (svgRef.current && zoomBehaviorRef.current) {
      d3.select(svgRef.current).transition().duration(250).call(zoomBehaviorRef.current.scaleBy, 0.8);
    }
  };

  const handleResetZoom = () => {
    if (svgRef.current && zoomBehaviorRef.current) {
      d3.select(svgRef.current).transition().duration(300).call(zoomBehaviorRef.current.transform, d3.zoomIdentity);
    }
  };

  useEffect(() => {
    if (!svgRef.current || !nodes.length) return;

    const width = containerRef.current?.clientWidth || 750;
    const height = 440;

    // Clear previous SVG contents
    d3.select(svgRef.current).selectAll('*').remove();

    const svg = d3.select(svgRef.current)
      .attr('viewBox', [0, 0, width, height])
      .attr('class', 'w-full h-full bg-slate-950 rounded-xl cursor-grab active:cursor-grabbing select-none');

    // Arrowhead Definitions
    const defs = svg.append('defs');

    // Default arrow marker
    defs.append('marker')
      .attr('id', 'arrow-default')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 26)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', '#64748b');

    // Interface/Contract arrow marker
    defs.append('marker')
      .attr('id', 'arrow-contract')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 26)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', '#38bdf8');

    // Caller / Risk arrow marker
    defs.append('marker')
      .attr('id', 'arrow-risk')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 26)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', '#f43f5e');

    // Target Glow Filter
    const filter = defs.append('filter')
      .attr('id', 'd3-glow-target')
      .attr('x', '-50%')
      .attr('y', '-50%')
      .attr('width', '200%')
      .attr('height', '200%');
    filter.append('feGaussianBlur').attr('stdDeviation', '6').attr('result', 'blur');
    filter.append('feComposite').attr('in', 'SourceGraphic').attr('in2', 'blur').attr('operator', 'over');

    const g = svg.append('g');

    // Pan / Zoom behavior
    const zoomBehavior = d3.zoom()
      .scaleExtent([0.3, 3])
      .on('zoom', (event) => g.attr('transform', event.transform));

    zoomBehaviorRef.current = zoomBehavior;
    svg.call(zoomBehavior);

    // Deep clone data for D3 simulation mutation
    const simNodes = nodes.map(n => ({
      ...n,
      x: n.x || width / 2 + (Math.random() - 0.5) * 100,
      y: n.y || height / 2 + (Math.random() - 0.5) * 100
    }));

    const validNodeMap = new Map(simNodes.map(n => [n.id, n]));
    const targetNode = simNodes.find(sn => sn.type === 'TARGET') || simNodes[0];

    const simEdges = edges
      .map(e => {
        let src = e.from;
        let dst = e.to;
        if (src === 'target' && !validNodeMap.has('target') && targetNode) src = targetNode.id;
        if (dst === 'target' && !validNodeMap.has('target') && targetNode) dst = targetNode.id;
        return {
          source: src,
          target: dst,
          label: e.label || '',
          hop: e.hop || ''
        };
      })
      .filter(e => validNodeMap.has(e.source) && validNodeMap.has(e.target));

    // Force Simulation Setup
    const simulation = d3.forceSimulation(simNodes)
      .force('link', d3.forceLink(simEdges).id(d => d.id).distance(120))
      .force('charge', d3.forceManyBody().strength(-380))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(44));

    // Render Edges
    const link = g.append('g')
      .selectAll('line')
      .data(simEdges)
      .enter()
      .append('line')
      .attr('stroke', d => {
        if (d.label?.includes('IMPLEMENTS') || d.label?.includes('EXTENDS')) return '#38bdf8';
        if (d.label?.includes('CALLS')) return '#f43f5e';
        return '#475569';
      })
      .attr('stroke-dasharray', d => (d.label?.includes('IMPLEMENTS') || d.label?.includes('EXTENDS')) ? '4,3' : 'none')
      .attr('stroke-width', d => d.label?.includes('CALLS') ? 2.2 : 1.8)
      .attr('marker-end', d => {
        if (d.label?.includes('IMPLEMENTS') || d.label?.includes('EXTENDS')) return 'url(#arrow-contract)';
        if (d.label?.includes('CALLS')) return 'url(#arrow-risk)';
        return 'url(#arrow-default)';
      });

    // Render Edge Label Badges
    const edgeLabelGroups = g.append('g')
      .selectAll('g')
      .data(simEdges)
      .enter()
      .append('g');

    edgeLabelGroups.append('rect')
      .attr('rx', 4)
      .attr('ry', 4)
      .attr('fill', '#090d16')
      .attr('stroke', d => (d.label?.includes('IMPLEMENTS') || d.label?.includes('EXTENDS')) ? '#38bdf8' : '#334155')
      .attr('stroke-width', 0.8)
      .attr('width', 52)
      .attr('height', 16);

    edgeLabelGroups.append('text')
      .text(d => d.label || '')
      .attr('font-size', '8.5px')
      .attr('font-family', 'monospace')
      .attr('font-weight', 'bold')
      .attr('fill', d => (d.label?.includes('IMPLEMENTS') || d.label?.includes('EXTENDS')) ? '#38bdf8' : '#cbd5e1')
      .attr('text-anchor', 'middle')
      .attr('dy', 11)
      .attr('dx', 26);

    // Render Nodes Group
    const node = g.append('g')
      .selectAll('g')
      .data(simNodes)
      .enter()
      .append('g')
      .attr('class', 'cursor-pointer')
      .call(d3.drag()
        .on('start', (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on('drag', (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on('end', (event, d) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        })
      );

    // Node Type Color Mapping
    const getNodeColor = (type) => {
      switch (type) {
        case 'TARGET': return '#ef4444';       // Red
        case 'DIRECT_CALLER': return '#f59e0b'; // Amber
        case 'TRANSITIVE_CALLER': return '#eab308'; // Yellow
        case 'INTERFACE': return '#38bdf8';     // Sky Blue
        case 'SUPERCLASS': return '#818cf8';    // Indigo
        case 'IMPLEMENTATION': return '#10b981';// Emerald
        case 'CALLEE': return '#06b6d4';        // Cyan
        default: return '#6366f1';              // Slate
      }
    };

    // Pulsing Outer Shockwave for Target Nodes
    node.filter(d => d.type === 'TARGET')
      .append('circle')
      .attr('r', 28)
      .attr('fill', 'none')
      .attr('stroke', '#ef4444')
      .attr('stroke-width', 2)
      .attr('opacity', 0.4)
      .attr('class', 'animate-ping');

    // Outer Node Circle
    node.append('circle')
      .attr('r', d => d.type === 'TARGET' ? 20 : 16)
      .attr('fill', '#0f172a')
      .attr('stroke', d => getNodeColor(d.type))
      .attr('stroke-width', d => (selectedNodeId === d.id ? 3.5 : 2.5))
      .attr('filter', d => d.type === 'TARGET' ? 'url(#d3-glow-target)' : null);

    // Inner Node Icon / Symbol Indicator
    node.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', 4)
      .attr('font-size', d => d.type === 'TARGET' ? '12px' : '10px')
      .attr('fill', '#f8fafc')
      .text(d => {
        if (d.type === 'TARGET') return '⚡';
        if (d.type === 'INTERFACE') return '📋';
        if (d.type === 'IMPLEMENTATION') return '🧩';
        if (d.type?.includes('CALLER')) return '📞';
        return '🔹';
      });

    // Node Label Badge below circle
    const labelGroup = node.append('g').attr('transform', d => `translate(0, ${d.type === 'TARGET' ? 32 : 28})`);

    labelGroup.append('rect')
      .attr('x', -60)
      .attr('y', -9)
      .attr('width', 120)
      .attr('height', 18)
      .attr('rx', 4)
      .attr('fill', '#090d16')
      .attr('stroke', d => (selectedNodeId === d.id ? '#06b6d4' : '#1e293b'))
      .attr('stroke-width', 1);

    labelGroup.append('text')
      .text(d => {
        const text = d.label || d.id;
        return text.length > 18 ? text.substring(0, 16) + '...' : text;
      })
      .attr('text-anchor', 'middle')
      .attr('dy', 3)
      .attr('fill', '#e2e8f0')
      .attr('font-size', '9.5px')
      .attr('font-family', 'monospace')
      .attr('font-weight', '600');

    // Node Click Handler
    node.on('click', (event, d) => {
      if (onSelectNode) onSelectNode(d.id, d);
    });

    // Hover Tooltips
    node.on('mouseenter', (event, d) => {
      const rect = containerRef.current.getBoundingClientRect();
      setTooltip({
        x: event.clientX - rect.left,
        y: event.clientY - rect.top - 12,
        data: d
      });
    }).on('mouseleave', () => setTooltip(null));

    // Simulation Tick Updates
    simulation.on('tick', () => {
      link
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);

      edgeLabelGroups.attr('transform', d => {
        const mx = (d.source.x + d.target.x) / 2 - 26;
        const my = (d.source.y + d.target.y) / 2 - 8;
        return `translate(${mx}, ${my})`;
      });

      node.attr('transform', d => `translate(${d.x},${d.y})`);
    });

    return () => simulation.stop();
  }, [graphData, selectedNodeId, onSelectNode]);

  const riskBadgeClass =
    riskLevel === 'HIGH' || (typeof riskScore === 'string' && parseFloat(riskScore) >= 6.5)
      ? 'bg-red-950/80 text-red-300 border-red-500/40'
      : riskLevel === 'MEDIUM' || (typeof riskScore === 'string' && parseFloat(riskScore) >= 3.5)
      ? 'bg-amber-950/80 text-amber-300 border-amber-500/40'
      : 'bg-emerald-950/80 text-emerald-300 border-emerald-500/40';

  return (
    <div ref={containerRef} className="relative w-full border border-slate-800 rounded-2xl overflow-hidden bg-slate-950 flex flex-col shadow-2xl">
      {/* Top Visualizer Control Bar */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-slate-900/90 border-b border-slate-800">
        <div className="flex items-center space-x-2.5">
          <Layers className="w-4 h-4 text-cyan-400" />
          <span className="text-xs font-bold text-slate-200">
            Blast Radius Engine: <span className="text-cyan-300 font-mono">{targetName}</span>
          </span>
          <span className="text-[10px] text-slate-500 font-mono hidden sm:inline">
            ({nodes.length} nodes, {edges.length} edges)
          </span>
        </div>

        <div className="flex items-center space-x-2">
          {/* Risk Score Pill */}
          <div className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-full border text-[11px] font-mono font-bold ${riskBadgeClass}`}>
            <ShieldAlert className="w-3.5 h-3.5" />
            <span>Risk Score: {riskScore}</span>
          </div>

          {/* D3 Zoom & Center Controls */}
          <div className="flex items-center bg-slate-950 border border-slate-800 rounded-lg p-0.5 ml-2">
            <button
              onClick={handleZoomIn}
              className="p-1 hover:bg-slate-800 text-slate-400 hover:text-slate-100 rounded transition"
              title="Zoom In"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={handleZoomOut}
              className="p-1 hover:bg-slate-800 text-slate-400 hover:text-slate-100 rounded transition"
              title="Zoom Out"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={handleResetZoom}
              className="p-1 hover:bg-slate-800 text-slate-400 hover:text-slate-100 rounded transition"
              title="Reset View"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* SVG Force-Directed Simulation Viewport */}
      <div className="relative w-full h-[420px] bg-[radial-gradient(#1e293b_1px,transparent_1px)] [background-size:18px_18px] overflow-hidden">
        <svg ref={svgRef} className="w-full h-full"></svg>

        {/* Legend */}
        <div className="absolute bottom-3 left-3 bg-slate-900/90 border border-slate-800 backdrop-blur rounded-xl p-2.5 text-[10px] font-mono space-y-1 shadow-lg pointer-events-none">
          <div className="font-bold text-slate-400 pb-1 border-b border-slate-800 mb-1">
            Node Types
          </div>
          <div className="flex items-center space-x-2">
            <span className="h-2 w-2 rounded-full bg-red-500"></span>
            <span className="text-slate-300">Target Symbol</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="h-2 w-2 rounded-full bg-amber-500"></span>
            <span className="text-slate-300">Direct Caller (1st Hop)</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="h-2 w-2 rounded-full bg-sky-400"></span>
            <span className="text-slate-300">Interface Contract</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="h-2 w-2 rounded-full bg-emerald-500"></span>
            <span className="text-slate-300">Implementation / Subclass</span>
          </div>
        </div>

        {/* Hover Tooltip Overlay */}
        {tooltip && (
          <div
            className="absolute z-30 bg-slate-900/95 text-slate-100 border border-slate-700/80 rounded-xl px-3.5 py-2.5 text-xs shadow-2xl pointer-events-none transform -translate-x-1/2 -translate-y-full backdrop-blur font-mono"
            style={{ left: `${tooltip.x}px`, top: `${tooltip.y}px` }}
          >
            <div className="flex items-center space-x-1.5 pb-1 border-b border-slate-800 mb-1.5">
              <span className="font-bold text-cyan-300">{tooltip.data.label}</span>
            </div>
            <p className="text-slate-400 text-[11px]">
              File: <span className="text-slate-200">{tooltip.data.file || 'Unknown'}</span>
            </p>
            <p className="text-slate-400 text-[11px]">
              Type: <span className="text-cyan-400 font-bold">{tooltip.data.type || 'Node'}</span>
            </p>
            {tooltip.data.scope && (
              <p className="text-slate-400 text-[11px]">
                Scope: <span className="text-slate-200">{tooltip.data.scope}</span>
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
