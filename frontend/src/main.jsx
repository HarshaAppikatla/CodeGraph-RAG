import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary
      title="CodeGraph Application Runtime Notice"
      description="An unhandled exception occurred in the application tree. Click retry below to reload the workspace."
    >
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
