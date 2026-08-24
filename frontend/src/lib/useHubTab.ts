import { useLocation, useNavigate } from 'react-router-dom'

/**
 * Drives a "hub" page's tab bar off the URL instead of local component
 * state — so every old sidebar sub-page's route (e.g. `/chills/upload`,
 * `/chills/videos`, `/chills/analytics`) still resolves to something real:
 * they all render the same hub, each landing on the matching tab. Switching
 * tabs updates the URL (replace, not push, so the back button doesn't have
 * to click through every tab you visited) — a refresh or a bookmark to any
 * of the old paths lands on the right tab.
 */
export function useHubTab(paths: Record<string, string>, defaultTab: string) {
  const location = useLocation()
  const navigate = useNavigate()
  const activeTab =
    Object.entries(paths).find(([, path]) => path === location.pathname)?.[0] ?? defaultTab
  const setTab = (tab: string) => {
    const path = paths[tab]
    if (path && path !== location.pathname) navigate(path, { replace: true })
  }
  return { activeTab, setTab }
}
