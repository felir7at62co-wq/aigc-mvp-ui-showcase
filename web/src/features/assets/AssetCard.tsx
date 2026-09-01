import { mediaUrl } from '../../api/client'
import type { AssetRecord } from '../../api/types'
import { Button } from '../../components/Button'

interface AssetCardProps {
  projectName: string
  asset: AssetRecord
  selected: boolean
  onToggle: () => void
  onEdit: () => void
  onDelete: () => void
  onUpload: (file: File) => void
}

export function AssetCard({
  projectName,
  asset,
  selected,
  onToggle,
  onEdit,
  onDelete,
  onUpload,
}: AssetCardProps) {
  return (
    <article
      className={`asset-generation-card${selected ? ' selected' : ''}`}
      aria-label={`资产 ${asset.name}`}
      onDoubleClick={onEdit}
    >
      <div className="asset-generation-card-actions">
        <Button
          type="button"
          size="sm"
          variant={selected ? 'primary' : 'secondary'}
          aria-label={`选择${asset.name}`}
          onClick={onToggle}
        >
          {selected ? '✓' : '○'}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="danger"
          aria-label={`删除${asset.name}`}
          onClick={onDelete}
        >
          ×
        </Button>
      </div>

      <label className={`asset-generation-image${asset.image_path ? ' has-image' : ''}`}>
        {asset.image_path ? (
          <img src={mediaUrl(projectName, asset.image_path)} alt={`${asset.name}资产图`} />
        ) : (
          <span><b>＋</b>点击上传资产图</span>
        )}
        <input
          className="visually-hidden"
          type="file"
          accept="image/png,image/jpeg,image/webp"
          aria-label={`上传${asset.name}图片`}
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (file) onUpload(file)
            event.target.value = ''
          }}
        />
      </label>

      <button type="button" className="asset-generation-meta" onClick={onToggle}>
        <strong>{asset.name}</strong>
        <span>别名：{asset.aliases.length ? asset.aliases.join('、') : '—'}</span>
        <span>集数：{asset.episodes.length ? asset.episodes.join(', ') : '—'}</span>
        <small>{asset.prompt || '暂无生成提示词，双击卡片补充。'}</small>
      </button>
      <Button type="button" size="sm" variant="secondary" onClick={onEdit}>
        编辑
      </Button>
    </article>
  )
}
