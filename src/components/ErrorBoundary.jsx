import React from "react";

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    // В консоли всегда будет видно, что именно упало — не тихо
    console.error("ErrorBoundary caught:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="fixed inset-0 flex flex-col items-center justify-center gap-3 px-6 text-center bg-background">
          <p className="text-sm text-muted-foreground">
            Что-то пошло не так. Попробуй обновить страницу.
          </p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium"
          >
            Обновить
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
