import { useRef, useState, type ChangeEvent, type DragEvent, type KeyboardEvent } from 'react'

export function ScriptFileDropzone({ file, onFileChange, onError }: {
  file: File | null
  onFileChange: (file: File) => void
  onError: (message: string) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const dragDepth = useRef(0)
  const [dragActive, setDragActive] = useState(false)

  function selectFile(nextFile?: File) {
    if (!nextFile) return
    if (!/\.(txt|docx)$/i.test(nextFile.name)) {
      onError('仅支持 .txt 或 .docx 剧本文件')
      return
    }
    onError('')
    onFileChange(nextFile)
  }

  function handleInputChange(event: ChangeEvent<HTMLInputElement>) {
    selectFile(event.target.files?.[0])
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'Enter' && event.key !== ' ') return
    event.preventDefault()
    inputRef.current?.click()
  }

  function handleDragEnter(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    dragDepth.current += 1
    setDragActive(true)
  }

  function handleDragLeave(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    dragDepth.current -= 1
    if (dragDepth.current <= 0) {
      dragDepth.current = 0
      setDragActive(false)
    }
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    dragDepth.current = 0
    setDragActive(false)
    selectFile(event.dataTransfer.files?.[0])
  }

  return (
    <div
      className={`script-dropzone${dragActive ? ' is-dragging' : ''}${file ? ' has-file' : ''}`}
      role="button"
      tabIndex={0}
      aria-label="上传剧本文件"
      onClick={() => inputRef.current?.click()}
      onKeyDown={handleKeyDown}
      onDragEnter={handleDragEnter}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <input
        ref={inputRef}
        className="script-dropzone-input"
        type="file"
        accept=".txt,.docx"
        onClick={(event) => {
          event.stopPropagation()
          event.currentTarget.value = ''
        }}
        onChange={handleInputChange}
      />
      <span className="script-dropzone-title">
        {file ? file.name : '点击或拖拽剧本文件到这里'}
      </span>
      <span className="script-dropzone-hint">
        {file ? '点击或拖拽可重新选择' : '支持 .txt、.docx'}
      </span>
    </div>
  )
}
