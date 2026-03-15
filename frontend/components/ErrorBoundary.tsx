
import React from 'react';

interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error;
}

/**
 * FE-UX-4: Global error boundary that catches render-time React errors.
 * Displays a friendly fallback UI with a retry (reset) option.
 */
export class ErrorBoundary extends React.Component<
  { children: React.ReactNode; fallbackMessage?: string },
  ErrorBoundaryState
> {
  constructor(props: any) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary] Unhandled render error:', error, info);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: undefined });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-[60vh] flex flex-col items-center justify-center gap-6 p-8 text-center">
          <div className="w-20 h-20 rounded-full bg-rose-50 flex items-center justify-center text-rose-500 text-4xl">
            <i className="fas fa-exclamation-triangle"></i>
          </div>
          <div>
            <h2 className="text-2xl font-bold text-slate-800 mb-2">
              {this.props.fallbackMessage ?? 'Something went wrong'}
            </h2>
            <p className="text-sm text-slate-500 max-w-md">
              An unexpected error occurred while rendering this view. The error has been logged.
            </p>
            {this.state.error && (
              <pre className="mt-4 p-3 bg-rose-50 text-rose-700 rounded-lg text-xs text-left overflow-auto max-w-lg max-h-32">
                {this.state.error.message}
              </pre>
            )}
          </div>
          <button
            onClick={this.handleRetry}
            className="px-6 py-2.5 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 transition-colors"
          >
            <i className="fas fa-redo mr-2"></i> Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
