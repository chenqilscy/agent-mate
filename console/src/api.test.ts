import { afterEach, describe, expect, it, vi } from 'vitest'

import { consoleApi } from './api'

describe('Console API session transport', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('requests an HttpOnly Console session without sending or storing a bearer token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      account: { id: 'account-1', name: 'Console User', is_platform_admin: false },
      expires_at: 123,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    const localStorage = { getItem: vi.fn(), setItem: vi.fn(), removeItem: vi.fn() }
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('localStorage', localStorage)

    await consoleApi.login('Console User', 'secret')

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(init.credentials).toBe('same-origin')
    expect(init.headers).toMatchObject({
      'X-AgentMate-Console-Session': '1',
    })
    expect(init.headers).not.toHaveProperty('Authorization')
    expect(localStorage.getItem).not.toHaveBeenCalled()
    expect(localStorage.setItem).not.toHaveBeenCalled()
  })
})
