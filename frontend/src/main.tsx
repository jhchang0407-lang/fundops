import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './styles/design-system.css'
import App from './App.tsx'

// Theme: light-first design language; warm dark via [data-theme="dark"].
// Applied before first paint so there is no flash of the wrong theme.
const savedTheme = localStorage.getItem('fundops.theme')
document.documentElement.dataset.theme = savedTheme === 'dark' ? 'dark' : 'light'

// Cost discipline: page views never trigger workflow runs. Queries are GET-only,
// cached for 30s, and never refetch on window focus.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
