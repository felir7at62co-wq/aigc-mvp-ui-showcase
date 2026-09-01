import type { MatchManifest, MatchShot, TimelineManifest } from '../../api/types'

export interface ScriptSection {
  shotNumber: number | null
  title: string
  body: string
}

export function shotNumberFromId(value: string): number | null {
  const match = value.match(/\d+/)
  return match ? Number(match[0]) : null
}

export function findShotMatch(
  manifest: MatchManifest | null | undefined,
  shotId: string,
): MatchShot | null {
  const shotNumber = shotNumberFromId(shotId)
  if (!manifest || shotNumber === null) return null
  return manifest.shots.find((shot) => shot.shot === shotNumber) ?? null
}

export function scriptSections(script: string): ScriptSection[] {
  const source = script.trim()
  if (!source) return []

  const headingPattern = /^镜头\s*(\d+)\s*[：:]\s*([^\r\n]*)/gm
  const headings = [...source.matchAll(headingPattern)]
  if (headings.length === 0) {
    return [{ shotNumber: null, title: '完整剧本', body: source }]
  }

  return headings.map((heading, index) => {
    const shotNumber = Number(heading[1])
    const start = (heading.index ?? 0) + heading[0].length
    const end = headings[index + 1]?.index ?? source.length
    const inlineDescription = String(heading[2] ?? '').trim()
    const remainder = source.slice(start, end).trim()
    return {
      shotNumber,
      title: `镜头${shotNumber}`,
      body: [inlineDescription, remainder].filter(Boolean).join('\n'),
    }
  })
}

export function firstActiveSegmentId(timeline: TimelineManifest | null | undefined): string | null {
  if (!timeline) return null
  return [...timeline.segments]
    .filter((segment) => !segment.deleted)
    .sort((a, b) => a.order - b.order)[0]?.id ?? null
}
