const HTTP_PROTOCOLS = new Set(['http:', 'https:'])

export function normalizeBackendUrl(
  value: string | undefined,
): string | undefined {
  const candidate = value?.trim()
  if (!candidate) {
    return undefined
  }

  let url: URL
  try {
    url = new URL(candidate)
  } catch {
    throw new Error(
      'VITE_BACKEND_URL must be a valid http:// or https:// URL.',
    )
  }

  if (!HTTP_PROTOCOLS.has(url.protocol)) {
    throw new Error(
      'VITE_BACKEND_URL must use the http:// or https:// scheme.',
    )
  }
  if (
    url.protocol === 'http:' &&
    typeof window !== 'undefined' &&
    window.location.protocol === 'https:'
  ) {
    throw new Error(
      'VITE_BACKEND_URL must use https:// when the frontend is served over HTTPS.',
    )
  }
  if (url.username || url.password) {
    throw new Error('VITE_BACKEND_URL must not include credentials.')
  }
  if (url.pathname !== '/' && url.pathname !== '') {
    throw new Error('VITE_BACKEND_URL must not include a path.')
  }
  if (url.search || url.hash) {
    throw new Error('VITE_BACKEND_URL must not include a query or fragment.')
  }

  return url.origin
}

export function apiUrl(
  path: string,
  backendUrl: string | undefined = import.meta.env.VITE_BACKEND_URL,
): string {
  const base = normalizeBackendUrl(backendUrl)
  if (!base) {
    return path
  }
  const suffix = path.startsWith('/') ? path : `/${path}`
  return `${base}${suffix}`
}

export function websocketUrlOverride(
  backendUrl: string | undefined = import.meta.env.VITE_BACKEND_URL,
  wsUrl: string | undefined = import.meta.env.VITE_WS_URL,
): string | undefined {
  const explicit = wsUrl?.trim()
  if (explicit) {
    return explicit
  }

  const base = normalizeBackendUrl(backendUrl)
  if (!base) {
    return undefined
  }
  return base.replace(/^http/, 'ws')
}
