/** Shared TypeScript types between renderer and main/backend */
export type PyInstallerOptions = {
  noconsole?: boolean
  add_data?: { src: string; dest: string }[]
  hidden_imports?: string[]
  paths?: string[]
  debug?: 'none'|'minimal'|'all'
  noupx?: boolean
  collect_all?: string[]
  collect_data?: string[]
  runtime_hooks?: string[]
  additional_hooks_dir?: string[]
}

export type CodeSign = {
  enable: boolean
  cert_path: string
  cert_password?: string
  timestamp_url?: string
  description?: string
  publisher?: string
}

export type BuildRequest = {
  project_path: string
  working_dir: string
  language: 'python'
  start_command: string
  output_type: 'exe'|'app'|'elf'
  include_env: boolean
  icon_path: string | null
  extra_files: string[]
  pyinstaller?: PyInstallerOptions
  pause_on_exit?: boolean
  pause_on_exit_seconds?: number
  win_autostart?: boolean
  autostart_method?: 'task'|'startup'
  code_sign?: CodeSign
  // Generate a helper script for Windows to launch the app via PowerShell
  win_smartscreen_helper?: boolean
  target_os?: 'windows'|'linux'|'macos'
  verbose?: boolean
  privacy_mask_logs?: boolean
}

export type BuildStatus = {
  build_id: string
  status: 'queued'|'running'|'success'|'failed'|'cancelled'
  started_at: string
  finished_at: string | null
  output_files: string[]
  error: string | null
}

export type LogEvent = {
  build_id: string
  timestamp: string
  level: 'info'|'warn'|'error'|'debug'
  message: string
}
