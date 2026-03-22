/**
 * API 封装 — 兼容 H5 和小程序
 *
 * H5 用 fetch，小程序用 uni.request，统一接口。
 */

const BASE_URL = ''  // 同源，通过 vite proxy 转发

export function request(url, options = {}) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: BASE_URL + url,
      method: options.method || 'GET',
      data: options.body ? JSON.parse(options.body) : options.data,
      header: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
        } else {
          reject(new Error(`API ${res.statusCode}`))
        }
      },
      fail: (err) => reject(err),
    })
  })
}

// 便捷方法
export const api = {
  get: (url) => request(url),
  post: (url, data) => request(url, { method: 'POST', data }),
}

// 录音相关
export const recordingApi = {
  list: () => api.get('/api/recordings'),
  get: (id) => api.get(`/api/recordings/${id}`),
  status: (id) => api.get(`/api/recordings/${id}/status`),
  reprocess: (id) => api.post(`/api/recordings/${id}/reprocess`),
  resummarize: (id) => api.post(`/api/recordings/${id}/resummarize`),
  delete: (id) => api.post(`/api/recordings/${id}/delete`),
  updateCategory: (id, category) => api.post(`/api/recordings/${id}/category`, { category }),
  setPrompt: (id, prompt) => api.post(`/api/recordings/${id}/prompt`, { prompt }),
}

// 上传（单独处理，用 uni.uploadFile）
export function uploadAudio(filePath) {
  return new Promise((resolve, reject) => {
    uni.uploadFile({
      url: BASE_URL + '/api/upload',
      filePath,
      name: 'file',
      success: (res) => {
        if (res.statusCode === 200) {
          resolve(JSON.parse(res.data))
        } else {
          reject(new Error(`Upload ${res.statusCode}`))
        }
      },
      fail: reject,
    })
  })
}

// 搜索
export const searchApi = {
  search: (q, type = 'hybrid') => api.get(`/api/search?q=${encodeURIComponent(q)}&type=${type}`),
}

// 说话人
export const speakerApi = {
  list: () => api.get('/api/speakers'),
  rename: (speakerId, newName) => api.post('/api/speakers/rename', { speaker_id: speakerId, new_name: newName }),
}

// 问答
export const chatApi = {
  ask: (question, conversationId = 'default') => api.post('/api/ask', { question, conversation_id: conversationId }),
  history: (conversationId = 'default') => api.get(`/api/chat/history?conversation_id=${conversationId}`),
  clear: (conversationId = 'default') => api.post(`/api/chat/clear?conversation_id=${conversationId}`),
}

// 分类
export const categoryApi = {
  list: () => api.get('/api/categories'),
  add: (category) => api.post('/api/categories', { category }),
}

// 术语
export const vocabApi = {
  list: () => api.get('/api/vocabulary'),
  add: (term, category) => api.post('/api/vocabulary', { term, category }),
  delete: (id) => api.post(`/api/vocabulary/${id}/delete`),
}

// 摘要模板
export const promptApi = {
  list: () => api.get('/api/summary-prompts'),
  builtin: (category) => api.get(`/api/summary-prompts/builtin/${encodeURIComponent(category)}`),
  save: (category, prompt) => api.post('/api/summary-prompts', { category, prompt }),
  delete: (id) => api.post(`/api/summary-prompts/${id}/delete`),
}
