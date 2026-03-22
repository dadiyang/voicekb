/**
 * 格式化工具
 */

export function relativeTime(dateStr) {
  const now = Date.now()
  const d = new Date(dateStr).getTime()
  const diff = Math.floor((now - d) / 1000)
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  if (diff < 172800) return '昨天'
  if (diff < 604800) return `${Math.floor(diff / 86400)}天前`
  return new Date(dateStr).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

export function friendlyDuration(seconds) {
  if (!seconds) return ''
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  if (m === 0) return `${s}秒`
  return s > 0 ? `${m}分${s}秒` : `${m}分钟`
}

export function formatTimestamp(seconds) {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

/**
 * 合并连续同一说话人的对话段
 */
export function mergeSegments(segments) {
  if (!segments?.length) return []
  const merged = []
  segments.forEach((seg, idx) => {
    const last = merged[merged.length - 1]
    if (last && last.speaker_id === seg.speaker_id && seg.start - last.end < 3) {
      last.texts.push(seg.text)
      last.end = seg.end
      last.indices.push(idx)
    } else {
      merged.push({
        speaker_id: seg.speaker_id,
        start: seg.start,
        end: seg.end,
        texts: [seg.text],
        indices: [idx],
      })
    }
  })
  return merged
}

/**
 * Markdown 渲染（简易版，小程序兼容）
 * 注：小程序内用 rich-text 组件渲染
 */
export function renderMarkdown(text) {
  if (!text) return ''
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/### (.+)/g, '<h4>$1</h4>')
    .replace(/## (.+)/g, '<h3>$1</h3>')
    .replace(/^- (.+)/gm, '<li>$1</li>')
    .replace(/^\d+\.\s+(.+)/gm, '<li>$1</li>')
    .replace(/---/g, '<hr/>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br/>')
}
