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

export interface ViewDefinitionResponse {
  uid: string
  name: string
  daten: Record<string, any>
  root: Record<string, any>
}

export interface ViewBaseRow {
  uid: string
  name: string
  daten: Record<string, any>
  historisch: number
  modified_at?: string | null
}

export interface ViewBaseResponse {
  view_guid: string
  table: string
  rows: ViewBaseRow[]
}

export interface ViewStateResponse {
  view_guid: string
  controls_source: Record<string, any>
  controls_effective: Array<Record<string, any>>
  table_state_source: Record<string, any>
  table_state_effective: Record<string, any>
  meta: Record<string, any>
}

export interface ViewStateUpdateRequest {
  controls_source?: Record<string, any>
  table_state_source?: Record<string, any>
}

export interface ViewMatrixRequest {
  controls_source?: Record<string, any>
  table_state_source?: Record<string, any>
  include_historisch?: boolean
  limit?: number
  offset?: number
}

export interface ViewTableOverrideOptions {
  table?: string | null
}

export type ViewMatrixRow =
  | ({ kind: 'group'; key: string; raw: any; count: number; sum?: number | null })
  | ({ kind: 'data'; group_key?: string } & ViewBaseRow)

export interface ViewMatrixResponse {
  view_guid: string
  table: string
  stichtag: number
  controls_source: Record<string, any>
  controls_effective: Array<Record<string, any>>
  table_state_source: Record<string, any>
  table_state_effective: Record<string, any>
  rows: ViewMatrixRow[]
  totals?: { count: number; sum?: number | null } | null
  dropdowns?: Record<string, any>
  meta: Record<string, any>
}

export interface FrameDefinitionResponse {
  uid: string
  name: string
  daten: Record<string, any>
  root: Record<string, any>
}

export interface DialogDefinitionResponse {
  uid: string
  name: string
  daten: Record<string, any>
  root: Record<string, any>
  root_table: string
  view_guid?: string | null
  edit_type: string
  selection_mode?: 'single' | 'multi' | string
  open_edit_mode?: 'button' | 'double_click' | 'auto' | string
  frame_guid?: string | null
  frame?: FrameDefinitionResponse | null
  meta: Record<string, any>
}

export interface DialogRow {
  uid: string
  name: string
}

export interface DialogRowsRequest {
  limit?: number
  offset?: number
}

export interface DialogRowsResponse {
  dialog_guid: string
  table: string
  rows: DialogRow[]
  meta: Record<string, any>
}

export interface DialogRecordResponse {
  uid: string
  name: string
  daten: Record<string, any>
  historisch: number
  modified_at?: string | null
}

export interface DialogRecordUpdateRequest {
  daten: Record<string, any>
}

export interface DialogLastCallResponse {
  key: string
  last_call: string | null
}

export interface DialogTableOverrideOptions {
  dialog_table?: string | null
}

export interface LookupRow {
  uid: string
  name: string
}

export interface LookupResponse {
  table: string
  rows: LookupRow[]
  meta: Record<string, any>
}

export interface MenuRecordResponse {
  uid: string
  name: string
  daten: Record<string, any>
}

export interface MenuRecordUpdateRequest {
  daten: Record<string, any>
}

export interface MenuCommandDefinition {
  handler: string
  label?: string
  params?: Array<Record<string, any>>
}

export interface MenuCommandCatalog {
  commands: MenuCommandDefinition[]
  language: string
  default_language: string
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

// Views API
export const viewsAPI = {
  getDefinition: async (viewGuid: string): Promise<ViewDefinitionResponse> => {
    const response = await api.get(`/views/${viewGuid}`)
    return response.data
  },

  getBase: async (viewGuid: string, limit: number = 200): Promise<ViewBaseResponse> => {
    const response = await api.get(`/views/${viewGuid}/base`, {
      params: { limit },
    })
    return response.data
  },

  getState: async (viewGuid: string, opts?: { table?: string; edit_type?: string }): Promise<ViewStateResponse> => {
    const response = await api.get(`/views/${viewGuid}/state`, {
      params: {
        ...(opts?.table ? { table: opts.table } : null),
        ...(opts?.edit_type ? { edit_type: opts.edit_type } : null),
      } as any,
    })
    return response.data
  },

  putState: async (viewGuid: string, controlsSource: Record<string, any>): Promise<ViewStateResponse> => {
    const response = await api.put(`/views/${viewGuid}/state`, {
      controls_source: controlsSource,
    } satisfies ViewStateUpdateRequest)
    return response.data
  },

  putStateFull: async (
    viewGuid: string,
    payload: ViewStateUpdateRequest,
    opts?: { table?: string; edit_type?: string },
  ): Promise<ViewStateResponse> => {
    const response = await api.put(`/views/${viewGuid}/state`, payload, {
      params: {
        ...(opts?.table ? { table: opts.table } : null),
        ...(opts?.edit_type ? { edit_type: opts.edit_type } : null),
      } as any,
    })
    return response.data
  },

  postMatrix: async (
    viewGuid: string,
    payload: ViewMatrixRequest,
    opts?: ViewTableOverrideOptions & { edit_type?: string },
  ): Promise<ViewMatrixResponse> => {
    const response = await api.post(`/views/${viewGuid}/matrix`, payload, {
      params: {
        ...(opts?.table ? { table: opts.table } : null),
        ...(opts?.edit_type ? { edit_type: opts.edit_type } : null),
      } as any,
    })
    return response.data
  },
}

// Dialogs API
export const dialogsAPI = {
  getDefinition: async (dialogGuid: string, opts?: DialogTableOverrideOptions): Promise<DialogDefinitionResponse> => {
    const response = await api.get(`/dialogs/${dialogGuid}`, {
      params: opts?.dialog_table ? { dialog_table: opts.dialog_table } : undefined,
    })
    return response.data
  },

  postRows: async (dialogGuid: string, payload: DialogRowsRequest, opts?: DialogTableOverrideOptions): Promise<DialogRowsResponse> => {
    const response = await api.post(`/dialogs/${dialogGuid}/rows`, payload, {
      params: opts?.dialog_table ? { dialog_table: opts.dialog_table } : undefined,
    })
    return response.data
  },

  getRecord: async (dialogGuid: string, recordUid: string, opts?: DialogTableOverrideOptions): Promise<DialogRecordResponse> => {
    const response = await api.get(`/dialogs/${dialogGuid}/record/${recordUid}`, {
      params: opts?.dialog_table ? { dialog_table: opts.dialog_table } : undefined,
    })
    return response.data
  },

  updateRecord: async (
    dialogGuid: string,
    recordUid: string,
    payload: DialogRecordUpdateRequest,
    opts?: DialogTableOverrideOptions
  ): Promise<DialogRecordResponse> => {
    const response = await api.put(`/dialogs/${dialogGuid}/record/${recordUid}`, payload, {
      params: opts?.dialog_table ? { dialog_table: opts.dialog_table } : undefined,
    })
    return response.data
  },

  putLastCall: async (
    dialogGuid: string,
    recordUid: string | null,
    opts?: DialogTableOverrideOptions
  ): Promise<DialogLastCallResponse> => {
    const response = await api.put(
      `/dialogs/${dialogGuid}/last-call`,
      {
        record_uid: recordUid,
      },
      {
        params: opts?.dialog_table ? { dialog_table: opts.dialog_table } : undefined,
      }
    )
    return response.data
  },
}

export const systemdatenAPI = {
  getMenuCommands: async (opts?: { language?: string; dataset_uid?: string }): Promise<MenuCommandCatalog> => {
    const response = await api.get('/systemdaten/menu-commands', {
      params: opts,
    })
    return response.data
  },
}

export const lookupsAPI = {
  get: async (table: string, opts?: { q?: string; limit?: number; offset?: number }): Promise<LookupResponse> => {
    const response = await api.get(`/lookups/${table}`, { params: opts })
    return response.data
  },
}

export const menuEditorAPI = {
  getMenu: async (menuGuid: string): Promise<MenuRecordResponse> => {
    const response = await api.get(`/menu-editor/${menuGuid}`)
    return response.data
  },

  updateMenu: async (menuGuid: string, payload: MenuRecordUpdateRequest): Promise<MenuRecordResponse> => {
    const response = await api.put(`/menu-editor/${menuGuid}`, payload)
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
  views: viewsAPI,
}
