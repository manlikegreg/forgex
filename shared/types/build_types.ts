/** Shared TypeScript types between renderer and main/backend */
export type ProtectEnvEncryption = {
  enable?: boolean
  mode?: 'inline'|'env'|'file'
  // If mode === 'inline', passphrase is embedded in the app (least secure; for dev only)
  passphrase?: string
  // If mode === 'env', runtime will read passphrase from this environment variable (default: FGX_ENV_KEY)
  env_var?: string
  // If mode === 'file', runtime will read passphrase from this file path (relative or absolute)
  file_path?: string
}

export type ProtectOptions = {
  enable?: boolean
  level?: 'basic'|'strong'|'max'
  obfuscate?: boolean
  anti_debug?: boolean
  integrity_check?: boolean
  mask_logs?: boolean
  encrypt_env?: ProtectEnvEncryption
}

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
  // Protection and hardening options for Python-only builds
  protect?: ProtectOptions
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
  // Windows Task Manager customization
  process_display_name?: string
  process_icon_path?: string
  extra_files: string[]
  pyinstaller?: PyInstallerOptions
  output_name?: string
  pause_on_exit?: boolean
  pause_on_exit_seconds?: number
  win_autostart?: boolean
  autostart_method?: 'task'|'startup'
  code_sign?: CodeSign
  // Generate a helper script for Windows to launch the app via PowerShell
  win_smartscreen_helper?: boolean
  // If helper generated, log output to file via CMD; optional custom log filename
  win_helper_log?: boolean
  win_helper_log_name?: string
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
