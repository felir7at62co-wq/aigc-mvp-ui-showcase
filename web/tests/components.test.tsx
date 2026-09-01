import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusBadge } from '../src/components/StatusBadge'
import { Button } from '../src/components/Button'
import { ProgressBar } from '../src/components/ProgressBar'

describe('StatusBadge', () => {
  it('映射状态到中文标签与语义色', () => {
    render(<StatusBadge status="completed" />)
    expect(screen.getByText('已完成')).toBeTruthy()
    expect(screen.getByText('已完成').className).toContain('success')
  })

  it('pending 显示待处理', () => {
    render(<StatusBadge status="pending" />)
    expect(screen.getByText('待处理')).toBeTruthy()
  })

  it('未知状态回退灰色', () => {
    render(<StatusBadge status="weird" />)
    expect(screen.getByText('weird')).toBeTruthy()
  })
})

describe('Button', () => {
  it('渲染主按钮并响应点击', () => {
    const onClick = vi.fn()
    render(<Button variant="primary" onClick={onClick}>开始</Button>)
    const button = screen.getByRole('button', { name: '开始' })
    button.click()
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('disabled 时不触发点击', () => {
    const onClick = vi.fn()
    render(<Button disabled onClick={onClick}>停用</Button>)
    screen.getByRole('button', { name: '停用' }).click()
    expect(onClick).not.toHaveBeenCalled()
  })
})

describe('ProgressBar', () => {
  it('按进度渲染宽度', () => {
    render(<ProgressBar value={40} />)
    const fill = document.querySelector('[data-testid="progress-fill"]')
    expect(fill).toBeTruthy()
    expect((fill as HTMLElement).style.width).toBe('40%')
  })
})
