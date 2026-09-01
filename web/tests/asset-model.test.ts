import { describe, expect, it } from 'vitest'
import {
  ASSET_CATEGORIES,
  toggleAssetSelection,
} from '../src/features/assets/model'

describe('asset page model', () => {
  it('keeps the expected category order and labels', () => {
    expect(ASSET_CATEGORIES).toEqual([
      { id: 'character', label: '角色' },
      { id: 'scene', label: '场景' },
      { id: 'prop', label: '道具' },
    ])
  })

  it('toggles a selected asset name without mutating the input set', () => {
    const selected = new Set(['主角'])
    const added = toggleAssetSelection(selected, '配角')
    const removed = toggleAssetSelection(added, '主角')

    expect([...selected]).toEqual(['主角'])
    expect([...added]).toEqual(['主角', '配角'])
    expect([...removed]).toEqual(['配角'])
  })
})
