import assert from 'node:assert/strict'
import {mkdtempSync, copyFileSync, readFileSync, writeFileSync, rmSync} from 'node:fs'
import {tmpdir} from 'node:os'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import {spawnSync} from 'node:child_process'
import {test} from 'node:test'

test('normalizes a disposable translation, not the repository', () => {
    const root = mkdtempSync(path.join(tmpdir(), 'obtainx-locales-'))
    try {
        copyFileSync(fileURLToPath(new URL('./standardize.mjs', import.meta.url)), path.join(root, 'standardize.mjs'))
        writeFileSync(path.join(root, 'en.json'), JSON.stringify({first: 'First', second: 'Second'}))
        writeFileSync(path.join(root, 'test.json'), JSON.stringify({obsolete: 'old', second: 'Translated'}))
        const result = spawnSync(process.execPath, [path.join(root, 'standardize.mjs')], {encoding: 'utf8'})
        assert.equal(result.status, 0, result.stderr)
        assert.match(result.stderr, /keys missing from template will be dropped: obsolete/)
        const text = readFileSync(path.join(root, 'test.json'), 'utf8')
        assert.deepEqual(Object.keys(JSON.parse(text)), ['first', 'second'])
        assert.deepEqual(JSON.parse(text), {first: 'First', second: 'Translated'})
    } finally {
        rmSync(root, {recursive: true, force: true})
    }
})

test('invalid JSON is a nonzero failure', () => {
    const root = mkdtempSync(path.join(tmpdir(), 'obtainx-locales-invalid-'))
    try {
        copyFileSync(fileURLToPath(new URL('./standardize.mjs', import.meta.url)), path.join(root, 'standardize.mjs'))
        writeFileSync(path.join(root, 'en.json'), '{invalid')
        const result = spawnSync(process.execPath, [path.join(root, 'standardize.mjs')], {encoding: 'utf8'})
        assert.notEqual(result.status, 0)
        assert.equal(readFileSync(path.join(root, 'en.json'), 'utf8'), '{invalid')
    } finally {
        rmSync(root, {recursive: true, force: true})
    }
})
