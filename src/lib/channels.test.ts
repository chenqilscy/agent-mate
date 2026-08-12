import { describe, expect, it } from 'vitest'

import { ChannelUnavailableError, validateServerRoot } from './channels'

describe('validateServerRoot', () => {
  it('normalizes a configured API URL to the Server origin', () => {
    expect(validateServerRoot(' https://server.example.test/api/ ')).toBe('https://server.example.test')
  })

  it.each(['not a url', 'ftp://server.example.test'])('rejects an unsafe Server root: %s', (value) => {
    expect(() => validateServerRoot(value)).toThrow(ChannelUnavailableError)
  })
})
