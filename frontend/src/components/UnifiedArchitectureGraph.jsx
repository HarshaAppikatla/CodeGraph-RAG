import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import * as d3 from 'd3';
import {
  Layers, Filter, Search, ZoomIn, ZoomOut, RefreshCw, Maximize2,
  GitBranch, Shield, ArrowRight, Activity, FileCode, Check, Eye, EyeOff
} from 'lucide-react';

const RELATION_STYLES = {
  EXTENDS: {
    color: '#38bdf8', // Sky blue
    dash: '6,4',
    width: 2.4,
    label: '[:EXTENDS]',
    name: 'Class Inheritance',
    description: 'SubClass extends SuperClass'
  },
  IMPLEMENTS: {
    color: '#06b6d4', // Cyan
    dash: '3,3',
    width: 2.2,
    label: '[:IMPLEMENTS]',
    name: 'Interface Contract',
    description: 'Class implements Interface'
  },
  HAS_METHOD: {
    color: '#10b981', // Emerald
    dash: 'none',
    width: 1.6,
    label: '[:HAS_METHOD]',
    name: 'Class Method',
    description: 'Class defines Method'
  },
  CALLS: {
    color: '#f43f5e', // Rose
    dash: 'none',
    width: 2.2,
    label: '[:CALLS]',
    name: 'Function Invocation',
    description: 'Caller invokes Callee'
  },
  CONTAINS: {
    color: '#f59e0b', // Amber
    dash: '4,4',
    width: 1.4,
    label: '[:CONTAINS]',
    name: 'File Containment',
    description: 'File contains Class/Symbol'
  },
  IMPORTS: {
    color: '#818cf8', // Indigo
    dash: '2,2',
    width: 1.2,
    label: '[:IMPORTS]',
    name: 'Cross-File Import',
    description: 'File imports Module'
  }
};

const NODE_TYPE_STYLES = {
  CLASS: {
    bg: '#0f172a',
    border: '#38bdf8',
    glow: '#0284c7',
    icon: '🏛️',
    radius: 22,
    labelColor: '#e0f2fe'
  },
  INTERFACE: {
    bg: '#0f172a',
    border: '#06b6d4',
    glow: '#0891b2',
    icon: '📋',
    radius: 20,
    labelColor: '#cffafe'
  },
  METHOD: {
    bg: '#0f172a',
    border: '#10b981',
    glow: '#059669',
    icon: '⚡',
    radius: 15,
    labelColor: '#d1fae5'
  },
  FILE: {
    bg: '#090d16',
    border: '#f59e0b',
    glow: '#d97706',
    icon: '📦',
    radius: 17,
    labelColor: '#fef3c7'
  },
  SYMBOL: {
    bg: '#0f172a',
    border: '#6366f1',
    glow: '#4f46e5',
    icon: '🔹',
    radius: 15,
    labelColor: '#e0e7ff'
  }
};

export const UnifiedArchitectureGraph = ({
  graphData,
  onFocusSymbol,
  isLoading = false
}) => {
  const svgRef = useRef(null);
  const containerRef = useRef(null);
  const zoomBehaviorRef = useRef(null);

  const [selectedNode, setSelectedNode] = useState(null);
  const [hoveredNode, setHoveredNode] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');

  // Relation Filters (all enabled by default)
  const [activeRelations, setActiveRelations] = useState({
    EXTENDS: true,
    IMPLEMENTS: true,
    HAS_METHOD: true,
    CALLS: true,
    CONTAINS: true,
    IMPORTS: true
  });

  // Node Type Filters
  const [activeNodeTypes, setActiveNodeTypes] = useState({
    CLASS: true,
    INTERFACE: true,
    METHOD: true,
    FILE: true,
    SYMBOL: true
  });

  const rawNodes = graphData?.nodes || [];
  const rawEdges = graphData?.edges || [];

  // Filtered dataset
  const { visibleNodes, visibleEdges } = useMemo(() => {
    const allowedNodeTypes = new Set(
      Object.keys(activeNodeTypes).filter(k => activeNodeTypes[k])
    );
    const allowedRelations = new Set(
      Object.keys(activeRelations).filter(k => activeRelations[k])
    );

    const validNodeMap = new Map();
    rawNodes.forEach(node => {
      const type = node.type || 'SYMBOL';
      if (allowedNodeTypes.has(type)) {
        validNodeMap.set(node.id, node);
      }
    });

    const validEdges = rawEdges.filter(edge => {
      const relType = edge.relationType || (edge.label?.replace(/\[:|\]/g, '')) || 'RELATES';
      return (
        allowedRelations.has(relType) &&
        validNodeMap.has(edge.from) &&
        validNodeMap.has(edge.to)
      );
    });

    return {
      visibleNodes: Array.from(validNodeMap.values()),
      visibleEdges: validEdges
    };
  }, [rawNodes, rawEdges, activeRelations, activeNodeTypes]);

  // Quick Presets
  const applyPreset = (preset) => {
    if (preset === 'ALL') {
      setActiveRelations({ EXTENDS: true, IMPLEMENTS: true, HAS_METHOD: true, CALLS: true, CONTAINS: true, IMPORTS: true });
      setActiveNodeTypes({ CLASS: true, INTERFACE: true, METHOD: true, FILE: true, SYMBOL: true });
    } else if (preset === 'INHERITANCE') {
      // Pure UML Class Hierarchy
      setActiveRelations({ EXTENDS: true, IMPLEMENTS: true, HAS_METHOD: false, CALLS: false, CONTAINS: false, IMPORTS: false });
      setActiveNodeTypes({ CLASS: true, INTERFACE: true, METHOD: false, FILE: false, SYMBOL: false });
    } else if (preset === 'CALLS') {
      // Runtime Call Flows
      setActiveRelations({ EXTENDS: false, IMPLEMENTS: false, HAS_METHOD: true, CALLS: true, CONTAINS: false, IMPORTS: false });
      setActiveNodeTypes({ CLASS: true, INTERFACE: false, METHOD: true, FILE: false, SYMBOL: false });
    } else if (preset === 'CLASSES') {
      // Classes & Their Member Methods
      setActiveRelations({ EXTENDS: true, IMPLEMENTS: true, HAS_METHOD: true, CALLS: false, CONTAINS: false, IMPORTS: false });
      setActiveNodeTypes({ CLASS: true, INTERFACE: true, METHOD: true, FILE: false, SYMBOL: false });
    }
  };

  // Zoom handlers
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

  // D3 Graph Simulation Render Effect
  useEffect(() => {
    if (!svgRef.current || !visibleNodes.length) return;

    const width = containerRef.current?.clientWidth || 800;
    const height = 520;

    d3.select(svgRef.current).selectAll('*').remove();

    const svg = d3.select(svgRef.current)
      .attr('viewBox', [0, 0, width, height])
      .attr('class', 'w-full h-full bg-slate-950 rounded-2xl cursor-grab active:cursor-grabbing select-none');

    const defs = svg.append('defs');

    // Create marker arrowheads for each relation type
    Object.keys(RELATION_STYLES).forEach(relKey => {
      const style = RELATION_STYLES[relKey];
      defs.append('marker')
        .attr('id', `marker-${relKey}`)
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 28)
        .attr('refY', 0)
        .attr('markerWidth', 6.5)
        .attr('markerHeight', 6.5)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', relKey === 'EXTENDS' ? 'M0,-5L10,0L0,5Z' : 'M0,-5L10,0L0,5')
        .attr('fill', relKey === 'EXTENDS' ? '#0f172a' : style.color)
        .attr('stroke', style.color)
        .attr('stroke-width', relKey === 'EXTENDS' ? 1.5 : 1);
    });

    const g = svg.append('g');

    // Pan / Zoom Behavior
    const zoomBehavior = d3.zoom()
      .scaleExtent([0.2, 3.5])
      .on('zoom', (event) => g.attr('transform', event.transform));

    zoomBehaviorRef.current = zoomBehavior;
    svg.call(zoomBehavior);

    // Deep copy for simulation
    const simNodes = visibleNodes.map(n => ({
      ...n,
      x: n.x || width / 2 + (Math.random() - 0.5) * 200,
      y: n.y || height / 2 + (Math.random() - 0.5) * 200
    }));

    const nodeIndexMap = new Map(simNodes.map(n => [n.id, n]));

    const simEdges = visibleEdges
      .map(e => ({
        source: nodeIndexMap.get(e.from),
        target: nodeIndexMap.get(e.to),
        label: e.label,
        relationType: e.relationType || (e.label?.replace(/\[:|\]/g, '')) || 'RELATES'
      }))
      .filter(e => e.source && e.target);

    // D3 Force Simulation
    const simulation = d3.forceSimulation(simNodes)
      .force('link', d3.forceLink(simEdges).id(d => d.id).distance(d => {
        if (d.relationType === 'HAS_METHOD') return 70;
        if (d.relationType === 'EXTENDS' || d.relationType === 'IMPLEMENTS') return 120;
        return 110;
      }))
      .force('charge', d3.forceManyBody().strength(-360))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(d => (NODE_TYPE_STYLES[d.type]?.radius || 18) + 16));

    // Render Relationship Edges
    const link = g.append('g')
      .selectAll('line')
      .data(simEdges)
      .enter()
      .append('line')
      .attr('stroke', d => RELATION_STYLES[d.relationType]?.color || '#475569')
      .attr('stroke-dasharray', d => RELATION_STYLES[d.relationType]?.dash || 'none')
      .attr('stroke-width', d => RELATION_STYLES[d.relationType]?.width || 1.6)
      .attr('marker-end', d => `url(#marker-${d.relationType})`)
      .attr('opacity', 0.85);

    // Edge Labels
    const edgeLabelGroup = g.append('g')
      .selectAll('g')
      .data(simEdges)
      .enter()
      .append('g');

    edgeLabelGroup.append('rect')
      .attr('rx', 3)
      .attr('ry', 3)
      .attr('fill', '#090d16')
      .attr('stroke', d => RELATION_STYLES[d.relationType]?.color || '#334155')
      .attr('stroke-width', 0.8)
      .attr('width', d => (d.label?.length || 8) * 6.5)
      .attr('height', 14)
      .attr('opacity', 0.9);

    edgeLabelGroup.append('text')
      .text(d => d.label || '')
      .attr('font-size', '8px')
      .attr('font-family', 'monospace')
      .attr('font-weight', 'bold')
      .attr('fill', d => RELATION_STYLES[d.relationType]?.color || '#cbd5e1')
      .attr('text-anchor', 'middle')
      .attr('dy', 10)
      .attr('dx', d => ((d.label?.length || 8) * 6.5) / 2);

    // Render Nodes
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

    // Outer Circle with distinct glow per type
    node.append('circle')
      .attr('r', d => NODE_TYPE_STYLES[d.type]?.radius || 18)
      .attr('fill', d => NODE_TYPE_STYLES[d.type]?.bg || '#0f172a')
      .attr('stroke', d => NODE_TYPE_STYLES[d.type]?.border || '#38bdf8')
      .attr('stroke-width', d => (selectedNode?.id === d.id ? 3.5 : 2.2))
      .attr('stroke-dasharray', d => d.type === 'INTERFACE' ? '3,3' : 'none');

    // Inner Emoji / Type Icon
    node.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', 4)
      .attr('font-size', d => d.type === 'CLASS' || d.type === 'INTERFACE' ? '12px' : '10px')
      .text(d => NODE_TYPE_STYLES[d.type]?.icon || '🔹');

    // Node Name Card
    const labelBox = node.append('g')
      .attr('transform', d => `translate(0, ${(NODE_TYPE_STYLES[d.type]?.radius || 18) + 12})`);

    labelBox.append('rect')
      .attr('x', d => -Math.min(d.label.length * 3.6 + 8, 70))
      .attr('y', -8)
      .attr('width', d => Math.min(d.label.length * 7.2 + 16, 140))
      .attr('height', 16)
      .attr('rx', 4)
      .attr('fill', '#090d16')
      .attr('stroke', d => (selectedNode?.id === d.id ? '#06b6d4' : '#1e293b'))
      .attr('stroke-width', 1);

    labelBox.append('text')
      .text(d => (d.label.length > 18 ? d.label.substring(0, 16) + '...' : d.label))
      .attr('text-anchor', 'middle')
      .attr('dy', 3.5)
      .attr('fill', d => NODE_TYPE_STYLES[d.type]?.labelColor || '#f1f5f9')
      .attr('font-size', '9px')
      .attr('font-family', 'monospace')
      .attr('font-weight', '600');

    // Node Interaction Handlers
    node.on('click', (event, d) => {
      setSelectedNode(d);
    });

    node.on('mouseenter', (event, d) => {
      setHoveredNode(d);
      // Highlight 1-hop neighborhood
      const neighborIds = new Set();
      neighborIds.add(d.id);
      simEdges.forEach(e => {
        if (e.source.id === d.id) neighborIds.add(e.target.id);
        if (e.target.id === d.id) neighborIds.add(e.source.id);
      });

      node.attr('opacity', nd => neighborIds.has(nd.id) ? 1 : 0.2);
      link.attr('opacity', e => (e.source.id === d.id || e.target.id === d.id) ? 1 : 0.1);
      edgeLabelGroup.attr('opacity', e => (e.source.id === d.id || e.target.id === d.id) ? 1 : 0.1);
    });

    node.on('mouseleave', () => {
      setHoveredNode(null);
      node.attr('opacity', 1);
      link.attr('opacity', 0.85);
      edgeLabelGroup.attr('opacity', 1);
    });

    // Simulation Tick Updates
    simulation.on('tick', () => {
      link
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);

      edgeLabelGroup.attr('transform', d => {
        const mx = (d.source.x + d.target.x) / 2 - ((d.label?.length || 8) * 6.5) / 2;
        const my = (d.source.y + d.target.y) / 2 - 7;
        return `translate(${mx}, ${my})`;
      });

      node.attr('transform', d => `translate(${d.x},${d.y})`);
    });

    return () => simulation.stop();
  }, [visibleNodes, visibleEdges, selectedNode]);

  // Compute connections of the selected node
  const selectedNodeRelations = useMemo(() => {
    if (!selectedNode) return { incoming: [], outgoing: [] };
    const incoming = rawEdges
      .filter(e => e.to === selectedNode.id)
      .map(e => ({
        fromNode: rawNodes.find(n => n.id === e.from) || { label: e.from, type: 'UNKNOWN' },
        label: e.label,
        type: e.relationType
      }));

    const outgoing = rawEdges
      .filter(e => e.from === selectedNode.id)
      .map(e => ({
        toNode: rawNodes.find(n => n.id === e.to) || { label: e.to, type: 'UNKNOWN' },
        label: e.label,
        type: e.relationType
      }));

    return { incoming, outgoing };
  }, [selectedNode, rawNodes, rawEdges]);

  return (
    <div ref={containerRef} className="flex-1 flex flex-col bg-slate-950 overflow-hidden relative">
      {/* Top Controls & Relation Legend Filter Bar */}
      <div className="border-b border-slate-800 bg-slate-900/40 p-3 space-y-2.5">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          {/* Header Title & Preset Chips */}
          <div className="flex items-center space-x-3">
            <div className="flex items-center space-x-2">
              <Layers className="h-4 w-4 text-cyan-400" />
              <span className="text-xs font-bold text-slate-100">
                Codebase Architecture & Knowledge Graph
              </span>
            </div>

            {/* Quick View Presets */}
            <div className="flex items-center bg-slate-950 border border-slate-800 p-0.5 rounded-lg text-[10px] font-bold">
              <button
                onClick={() => applyPreset('ALL')}
                className="px-2 py-0.5 rounded text-slate-300 hover:text-cyan-300 hover:bg-slate-800 transition"
                title="Show all connected classes, methods, and files"
              >
                All Relations
              </button>
              <button
                onClick={() => applyPreset('INHERITANCE')}
                className="px-2 py-0.5 rounded text-slate-300 hover:text-cyan-300 hover:bg-slate-800 transition"
                title="Show only Class and Interface Inheritance ([:EXTENDS] & [:IMPLEMENTS])"
              >
                UML Hierarchy
              </button>
              <button
                onClick={() => applyPreset('CALLS')}
                className="px-2 py-0.5 rounded text-slate-300 hover:text-rose-300 hover:bg-slate-800 transition"
                title="Show only Function Invocations ([:CALLS])"
              >
                Call Flows
              </button>
              <button
                onClick={() => applyPreset('CLASSES')}
                className="px-2 py-0.5 rounded text-slate-300 hover:text-emerald-300 hover:bg-slate-800 transition"
                title="Show Classes and their member Methods"
              >
                Class Structure
              </button>
            </div>
          </div>

          {/* Zoom and Search Controls */}
          <div className="flex items-center space-x-2">
            <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-0.5">
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

            <div className="text-[11px] font-mono text-slate-400 bg-slate-900 border border-slate-800 px-2.5 py-1 rounded-lg">
              <span className="text-cyan-400 font-bold">{visibleNodes.length}</span> nodes,{' '}
              <span className="text-emerald-400 font-bold">{visibleEdges.length}</span> relations
            </div>
          </div>
        </div>

        {/* Relationship Toggle Pills (The Core Feature: User Controls Relations) */}
        <div className="flex flex-wrap items-center gap-1.5 pt-1 border-t border-slate-800/80">
          <span className="text-[10px] uppercase tracking-wider font-mono text-slate-500 mr-1 flex items-center gap-1">
            <Filter className="w-3 h-3" /> Relations:
          </span>

          {Object.keys(RELATION_STYLES).map(relKey => {
            const style = RELATION_STYLES[relKey];
            const isActive = activeRelations[relKey];
            const edgeCount = rawEdges.filter(e => (e.relationType === relKey || e.label?.includes(relKey))).length;

            return (
              <button
                key={relKey}
                onClick={() => setActiveRelations(prev => ({ ...prev, [relKey]: !prev[relKey] }))}
                className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-bold flex items-center space-x-1 transition border ${
                  isActive
                    ? 'bg-slate-900 border-slate-700 text-slate-200 shadow-sm'
                    : 'bg-slate-950/40 border-slate-800/60 text-slate-600 line-through'
                }`}
                style={isActive ? { borderLeftColor: style.color, borderLeftWidth: '3px' } : {}}
                title={style.description}
              >
                <span
                  className="w-2 h-2 rounded-full inline-block"
                  style={{ backgroundColor: isActive ? style.color : '#475569' }}
                />
                <span>{style.label}</span>
                <span className="text-[9px] text-slate-500">({edgeCount})</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Interactive Canvas & Side Inspector Drawer */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Force-Directed Canvas */}
        <div className="flex-1 relative w-full h-full min-h-[440px] bg-[radial-gradient(#1e293b_1px,transparent_1px)] [background-size:18px_18px] overflow-hidden">
          <svg ref={svgRef} className="w-full h-full"></svg>

          {/* Canvas Floating Legend */}
          <div className="absolute bottom-3 left-3 bg-slate-900/90 border border-slate-800 backdrop-blur rounded-xl p-2.5 text-[10px] font-mono space-y-1 shadow-xl pointer-events-none">
            <div className="font-bold text-slate-400 pb-1 border-b border-slate-800 mb-1 flex items-center justify-between">
              <span>Entity Legend</span>
            </div>
            <div className="flex items-center space-x-2">
              <span>🏛️</span>
              <span className="text-sky-300 font-bold">Class</span>
            </div>
            <div className="flex items-center space-x-2">
              <span>📋</span>
              <span className="text-cyan-300 font-bold">Interface</span>
            </div>
            <div className="flex items-center space-x-2">
              <span>⚡</span>
              <span className="text-emerald-300 font-bold">Method</span>
            </div>
            <div className="flex items-center space-x-2">
              <span>📦</span>
              <span className="text-amber-300 font-bold">File</span>
            </div>
          </div>
        </div>

        {/* Selected Node Details Inspector Panel */}
        {selectedNode && (
          <div className="w-80 border-l border-slate-800 bg-slate-900/95 flex flex-col overflow-y-auto backdrop-blur font-mono text-xs p-4 space-y-4 shadow-2xl">
            {/* Header info */}
            <div className="flex items-start justify-between border-b border-slate-800 pb-3">
              <div>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
                  {selectedNode.type}
                </span>
                <h3 className="font-bold text-slate-100 text-sm mt-1.5 break-all">
                  {selectedNode.label}
                </h3>
                <p className="text-[10px] text-slate-400 mt-0.5 break-all">{selectedNode.file}</p>
              </div>
              <button
                onClick={() => setSelectedNode(null)}
                className="text-slate-500 hover:text-slate-200 text-xs p-1"
                title="Close Inspector"
              >
                ✕
              </button>
            </div>

            {/* Drill Down into Blast Radius */}
            {onFocusSymbol && (
              <button
                onClick={() => onFocusSymbol(selectedNode.label)}
                className="w-full py-1.5 px-3 bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/40 rounded-xl text-xs font-bold flex items-center justify-center space-x-2 transition shadow-lg"
              >
                <Activity className="h-3.5 w-3.5" />
                <span>Inspect Symbol Blast Radius</span>
              </button>
            )}

            {/* Scope / Signature Preview */}
            {selectedNode.signature && (
              <div className="space-y-1">
                <span className="text-[10px] uppercase text-slate-500 font-bold">Signature / Contract:</span>
                <div className="p-2 bg-slate-950 rounded-lg border border-slate-800 text-[11px] text-slate-300 overflow-x-auto leading-relaxed">
                  {selectedNode.signature}
                </div>
              </div>
            )}

            {/* Outgoing Relations (What this node extends, implements, calls, or contains) */}
            <div className="space-y-1.5">
              <span className="text-[10px] uppercase text-slate-400 font-bold">
                Outgoing Relations ({selectedNodeRelations.outgoing.length}):
              </span>
              {selectedNodeRelations.outgoing.length === 0 ? (
                <p className="text-[11px] text-slate-600 italic">No outgoing relations</p>
              ) : (
                <div className="space-y-1.5">
                  {selectedNodeRelations.outgoing.map((rel, idx) => (
                    <div
                      key={idx}
                      className="p-2 bg-slate-950/80 border border-slate-800/80 rounded-lg flex items-center justify-between text-[11px]"
                    >
                      <span className="text-slate-300 font-bold truncate">
                        {rel.toNode.label}
                      </span>
                      <span
                        className="px-1.5 py-0.5 rounded text-[9px] font-bold"
                        style={{
                          backgroundColor: `${RELATION_STYLES[rel.type]?.color || '#64748b'}20`,
                          color: RELATION_STYLES[rel.type]?.color || '#94a3b8',
                          border: `1px solid ${RELATION_STYLES[rel.type]?.color || '#64748b'}40`
                        }}
                      >
                        {rel.label}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Incoming Relations (What extends, calls, or contains this node) */}
            <div className="space-y-1.5">
              <span className="text-[10px] uppercase text-slate-400 font-bold">
                Incoming Relations ({selectedNodeRelations.incoming.length}):
              </span>
              {selectedNodeRelations.incoming.length === 0 ? (
                <p className="text-[11px] text-slate-600 italic">No incoming relations</p>
              ) : (
                <div className="space-y-1.5">
                  {selectedNodeRelations.incoming.map((rel, idx) => (
                    <div
                      key={idx}
                      className="p-2 bg-slate-950/80 border border-slate-800/80 rounded-lg flex items-center justify-between text-[11px]"
                    >
                      <span className="text-slate-300 font-bold truncate">
                        {rel.fromNode.label}
                      </span>
                      <span
                        className="px-1.5 py-0.5 rounded text-[9px] font-bold"
                        style={{
                          backgroundColor: `${RELATION_STYLES[rel.type]?.color || '#64748b'}20`,
                          color: RELATION_STYLES[rel.type]?.color || '#94a3b8',
                          border: `1px solid ${RELATION_STYLES[rel.type]?.color || '#64748b'}40`
                        }}
                      >
                        {rel.label}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
