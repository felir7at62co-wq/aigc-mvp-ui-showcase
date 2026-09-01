import { describe, expect, it } from 'vitest'
import type { MatchManifest, TimelineManifest } from '../src/api/types'
import {
  findShotMatch,
  firstActiveSegmentId,
  scriptSections,
  shotNumberFromId,
} from '../src/features/video-generation/model'

describe('video generation view model', () => {
  it('extracts a shot number from timeline identifiers', () => {
    expect(shotNumberFromId('shot-003')).toBe(3)
    expect(shotNumberFromId('01-014')).toBe(1)
    expect(shotNumberFromId('no-number')).toBeNull()
  })

  it('finds the matching asset manifest shot', () => {
    const manifest: MatchManifest = {
      version: 1,
      episode: '01',
      shots: [
        { shot: 3, characters: [], scene: { input: '', name: '', matched: false }, props: [] },
      ],
    }

    expect(findShotMatch(manifest, 'shot-003')?.shot).toBe(3)
    expect(findShotMatch(manifest, 'shot-004')).toBeNull()
  })

  it('splits a generated script into shot sections', () => {
    const sections = scriptSections('镜头1：\n画面描述：第一幕\n\n镜头2:\n画面描述：第二幕')

    expect(sections).toEqual([
      { shotNumber: 1, title: '镜头1', body: '画面描述：第一幕' },
      { shotNumber: 2, title: '镜头2', body: '画面描述：第二幕' },
    ])
  })

  it('selects the first non-deleted timeline segment', () => {
    const timeline = {
      segments: [
        { id: 'deleted', order: 0, deleted: true },
        { id: 'second', order: 2, deleted: false },
        { id: 'first', order: 1, deleted: false },
      ],
    } as TimelineManifest

    expect(firstActiveSegmentId(timeline)).toBe('first')
  })
})
