# Per-repo fleet start config for comms-mcp
# Edit ports/backend target here - start.ps1 is fleet-standard.
@{
    Name         = 'comms-mcp'
    BackendPort  = 10904
    FrontendPort = 10903
    HealthPath   = '/health'
    WebRoot      = 'web_sota'
    Backend = @{
        Kind          = 'uvicorn'
        UvicornTarget = 'comms_mcp.server:app'
        SyncExtras    = @('dev')
        Env           = @{ WEB_PORT = '10904' }
    }
    Frontend = @{
        Kind           = 'vite-npm'
        PackageManager = 'npm'
        PortEnvVar     = 'VITE_PORT'
        ApiTargetEnv   = 'VITE_API_TARGET'
    }
}
