import { Link } from 'react-router-dom'
import type { EpisodeSummary } from '../../api/types'

interface EpisodeRailProps {
  projectName: string
  currentEpisodeId: string
  episodes: EpisodeSummary[]
}

export function EpisodeRail({ projectName, currentEpisodeId, episodes }: EpisodeRailProps) {
  return (
    <nav className="video-episode-rail" aria-label="分集">
      <header className="video-column-head">
        <h2>分集</h2>
        <span>{episodes.length} 集</span>
      </header>
      <div className="video-episode-list">
        {episodes.map((episode) => {
          const isCurrent = episode.episode_id === currentEpisodeId
          return (
            <Link
              key={episode.episode_id}
              to={`/projects/${encodeURIComponent(projectName)}/episodes/${episode.episode_id}`}
              className={`video-episode-item${isCurrent ? ' active' : ''}`}
              aria-current={isCurrent ? 'page' : undefined}
            >
              <span className="video-episode-number">{episode.episode_id}</span>
              <span className="video-episode-copy">
                <strong>第 {episode.episode_id} 集</strong>
                <small>{episode.marker || '分集剧本'}</small>
              </span>
              <span
                className={`video-episode-state state-${episode.shot_match_status || 'pending'}`}
                title={episode.shot_match_status || 'pending'}
              />
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
