import type { MatchShot } from '../../api/types'

interface AssetMatchPanelProps {
  shot: MatchShot | null
  fallbackAssetIds: string[]
}

interface AssetItem {
  key: string
  kind: string
  input: string
  name: string | null
  matched: boolean
}

export function AssetMatchPanel({ shot, fallbackAssetIds }: AssetMatchPanelProps) {
  const assets: AssetItem[] = shot
    ? [
        ...shot.characters.map((item, index) => ({ ...item, key: `character-${index}`, kind: '角色' })),
        ...(shot.scene.input
          ? [{ ...shot.scene, key: 'scene', kind: '场景' }]
          : []),
        ...shot.props.map((item, index) => ({ ...item, key: `prop-${index}`, kind: '道具' })),
      ]
    : fallbackAssetIds.map((assetId, index) => ({
        key: `fallback-${index}`,
        kind: '资产',
        input: assetId,
        name: assetId,
        matched: true,
      }))
  const matchedCount = assets.filter((asset) => asset.matched).length

  return (
    <section className="video-production-panel video-asset-panel" aria-label="资产匹配">
      <header className="video-panel-head">
        <h2>资产匹配</h2>
        <span>{shot ? `镜头 ${String(shot.shot).padStart(3, '0')}` : '当前镜头'}</span>
      </header>
      <div className="video-asset-body">
        <div className={`video-asset-summary${assets.length > 0 && matchedCount === assets.length ? ' complete' : ''}`}>
          {assets.length ? `${matchedCount} / ${assets.length} 个资产已匹配` : '暂无资产匹配记录'}
        </div>
        <div className="video-asset-grid">
          {assets.map((asset) => (
            <article key={asset.key} className={`video-asset-card${asset.matched ? ' matched' : ' missing'}`}>
              <div className={`video-asset-thumb kind-${asset.kind}`}>{asset.kind.slice(0, 1)}</div>
              <div className="video-asset-info">
                <strong>{asset.name || asset.input}</strong>
                <span>{asset.kind} · {asset.matched ? '已匹配' : '待匹配'}</span>
              </div>
              <span className="video-asset-check" aria-label={asset.matched ? '已匹配' : '待匹配'}>
                {asset.matched ? '✓' : '!'}
              </span>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}
