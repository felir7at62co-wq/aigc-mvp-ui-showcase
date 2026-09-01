import { Button } from './Button'
import { StatusBadge } from './StatusBadge'

interface ExportPanelProps {
  mp4Status: string
  draftStatus: string
  onExportMp4: () => void
  onExportDraft: () => void
}

export function ExportPanel({
  mp4Status,
  draftStatus,
  onExportMp4,
  onExportDraft,
}: ExportPanelProps) {
  return (
    <div className="export-panel">
      <div className="export-row">
        <span>MP4 导出（预览下载）</span>
        <StatusBadge status={mp4Status} />
        <Button type="button" size="sm" onClick={onExportMp4}>导出 MP4</Button>
      </div>
      <div className="export-row">
        <span>剪映工程导出</span>
        <StatusBadge status={draftStatus} />
        <Button type="button" variant="secondary" size="sm" onClick={onExportDraft}>
          导出剪映工程
        </Button>
      </div>
    </div>
  )
}
