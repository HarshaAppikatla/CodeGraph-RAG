import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback || (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-center space-y-4 bg-slate-950">
            <div className="h-14 w-14 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-400 flex items-center justify-center shadow-lg">
              <AlertTriangle className="h-7 w-7" />
            </div>
            <h4 className="text-base font-bold text-slate-200">
              {this.props.title || 'Component Rendering Notice'}
            </h4>
            <p className="text-xs text-slate-400 max-w-md">
              {this.props.description || 'An unexpected error occurred while rendering this interactive visualization.'}
            </p>
            {this.state.error?.message && (
              <pre className="text-[11px] font-mono text-rose-300/80 bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 max-w-lg overflow-x-auto">
                {this.state.error.message}
              </pre>
            )}
            <button
              onClick={this.handleReset}
              className="px-4 py-2 bg-cyan-500 hover:bg-cyan-400 text-slate-950 text-xs font-bold rounded-xl flex items-center space-x-1.5 transition shadow-lg shadow-cyan-500/20"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              <span>Retry Component</span>
            </button>
          </div>
        )
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;

