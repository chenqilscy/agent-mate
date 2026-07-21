#!/usr/bin/env node
import { createHash } from 'node:crypto'
import { readFileSync, statSync } from 'node:fs'
import { resolve } from 'node:path'

const input = process.argv[2]
if (!input) throw new Error('usage: node scripts/validate-desktop-release.mjs <release.json>')
const source = resolve(input)
const payload = JSON.parse(readFileSync(source, 'utf8'))
if (!/^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(payload.version || '')) throw new Error('invalid semantic version')
if (!['stable', 'beta'].includes(payload.channel)) throw new Error('channel must be stable or beta')
if (!Array.isArray(payload.artifacts) || payload.artifacts.length === 0) throw new Error('signed artifacts are required')

const seen = new Set()
for (const artifact of payload.artifacts) {
  const key = `${artifact.target}/${artifact.arch}`
  if (!artifact.target || !artifact.arch || seen.has(key)) throw new Error(`duplicate or invalid artifact ${key}`)
  seen.add(key)
  if (!String(artifact.url || '').startsWith('https://')) throw new Error(`${key}: URL must use https`)
  if (String(artifact.signature || '').length < 32) throw new Error(`${key}: missing updater signature`)
  if (!/^[0-9a-f]{64}$/.test(String(artifact.sha256 || ''))) throw new Error(`${key}: invalid sha256`)
  if (!Number.isInteger(artifact.size_bytes) || artifact.size_bytes < 1) throw new Error(`${key}: invalid size_bytes`)
  if (artifact.file) {
    const file = resolve(source, '..', artifact.file)
    const bytes = readFileSync(file)
    const actual = createHash('sha256').update(bytes).digest('hex')
    if (actual !== artifact.sha256) throw new Error(`${key}: sha256 does not match ${artifact.file}`)
    if (statSync(file).size !== artifact.size_bytes) throw new Error(`${key}: size does not match ${artifact.file}`)
  }
}
process.stdout.write(JSON.stringify({ ok: true, version: payload.version, channel: payload.channel, artifacts: payload.artifacts.length }) + '\n')
