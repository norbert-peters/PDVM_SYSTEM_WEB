import axios from 'axios'

const API_BASE_URL = 'http://localhost:8000/api'

export interface LoginCredentials {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user_id: string
  email: string
  name?: string
  password_change_required?: boolean
  auto_select_mandant?: string | null
  user_data?: Record<string, any>
  mandanten?: Array<Record<string, any>>
}

export interface PdvmRecord {
  uid: string
  name: string
  daten: { [key: string]: any }
  modified_at?: string
}

export interface GcsStichtagResponse {
  stichtag: number
  iso: string | null
  display: string
}

// Create axios instance with default config
const api = axios.create({
  baseURL: API_BASE_URL,
})

// Request interceptor to automatically add token to all requests
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor for handling 401 errors globally
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Unauthorized - Token ungültig oder abgelaufen
      console.log('Token ungültig - automatischer Logout')
      localStorage.removeItem('token')
      localStorage.removeItem('mandant_id')
      // Reload page to trigger login screen
      window.location.href = '/'
    }
    return Promise.reject(error)
  }
)

// Auth API
export const authAPI = {
  login: async (credentials: LoginCredentials): Promise<LoginResponse> => {
    const formData = new FormData()
    formData.append('username', credentials.username)
    formData.append('password', credentials.password)
    
    const response = await api.post('/auth/login', formData)
    return response.data
  },
  
  getMe: async (token: string) => {
    const response = await api.get('/auth/me', {
      headers: { Authorization: `Bearer ${token}` }
    })
    return response.data
  },
}

// Tables API
export const tablesAPI = {
  getAll: async (tableName: string, token: string): Promise<PdvmRecord[]> => {
    const response = await api.get(`/tables/${tableName}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
    return response.data
  },
  
  getOne: async (tableName: string, uid: string, token: string): Promise<PdvmRecord> => {
    const response = await api.get(`/tables/${tableName}/${uid}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
    return response.data
  },
  
  create: async (tableName: string, data: any, token: string) => {
    const response = await api.post(`/tables/${tableName}`, data, {
      headers: { Authorization: `Bearer ${token}` }
    })
    return response.data
  },
  
  update: async (tableName: string, uid: string, data: any, token: string) => {
    const response = await api.put(`/tables/${tableName}/${uid}`, data, {
      headers: { Authorization: `Bearer ${token}` }
    })
    return response.data
  },
  
  delete: async (tableName: string, uid: string, token: string) => {
    const response = await api.delete(`/tables/${tableName}/${uid}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
    return response.data
  },
}

// Menu API
export const menuAPI = {
  getUserStartMenu: async (token: string) => {
    const response = await api.get('/menu/user/start', {
      headers: { Authorization: `Bearer ${token}` }
    })
    return response.data
  },
}

// Mandanten API
export const mandantenAPI = {
  getAll: async (token: string) => {
    const response = await api.get('/mandanten', {
      headers: { Authorization: `Bearer ${token}` }
    })
    return response.data
  },
  
  selectMandant: async (mandantId: string) => {
    const response = await api.post(`/mandanten/select`, { mandant_id: mandantId })
    return response.data
  },
}

// GCS API
export const gcsAPI = {
  getStichtag: async (): Promise<GcsStichtagResponse> => {
    const response = await api.get('/gcs/stichtag')
    return response.data
  },

  setStichtagIso: async (iso: string): Promise<{ success: boolean } & GcsStichtagResponse> => {
    const response = await api.post('/gcs/stichtag', { iso })
    return response.data
  },
}

// Export axios instance for backward compatibility
export const apiClient = api

// Default export for backward compatibility
export default {
  auth: authAPI,
  tables: tablesAPI,
  menu: menuAPI,
  mandanten: mandantenAPI,
  gcs: gcsAPI,
}
