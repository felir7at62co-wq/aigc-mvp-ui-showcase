import type { AssetCategory } from '../../api/types'

export const ASSET_CATEGORIES: Array<{ id: AssetCategory; label: string }> = [
  { id: 'character', label: '角色' },
  { id: 'scene', label: '场景' },
  { id: 'prop', label: '道具' },
]

export function toggleAssetSelection(selected: Set<string>, name: string) {
  const next = new Set(selected)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  return next
}
