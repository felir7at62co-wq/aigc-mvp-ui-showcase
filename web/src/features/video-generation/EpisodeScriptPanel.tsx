import { scriptSections } from './model'

interface EpisodeScriptPanelProps {
  episodeId: string
  script: string
  currentShotNumber: number | null
}

export function EpisodeScriptPanel({
  episodeId,
  script,
  currentShotNumber,
}: EpisodeScriptPanelProps) {
  const sections = scriptSections(script)

  return (
    <section className="video-script-column" aria-label="分集剧本">
      <header className="video-column-head">
        <h2>分集剧本</h2>
        <span>第 {episodeId} 集</span>
      </header>
      <div className="video-script-toolbar">
        <span className="active">整集剧本</span>
        <span>{sections.length ? `${sections.length} 个镜头` : '等待生成'}</span>
      </div>
      <div className="video-script-scroll">
        {sections.length === 0 && (
          <div className="video-panel-empty">当前分集还没有镜头脚本。</div>
        )}
        {sections.map((section, index) => (
          <article
            key={`${section.shotNumber ?? 'full'}-${index}`}
            className={`video-script-section${section.shotNumber === currentShotNumber ? ' active' : ''}`}
          >
            <div className="video-script-section-head">
              <strong>{section.title}</strong>
              {section.shotNumber !== null && <span>{String(section.shotNumber).padStart(3, '0')}</span>}
            </div>
            <pre>{section.body}</pre>
          </article>
        ))}
      </div>
    </section>
  )
}
