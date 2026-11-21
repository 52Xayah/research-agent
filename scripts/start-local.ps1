param(
    [Parameter(Mandatory)]
    [ValidateSet('api', 'ui', 'embedding')]
    [string] $Service,

    [ValidateRange(1, 65535)]
    [int] $ApiPort = 8000,

    [ValidateRange(1, 65535)]
    [int] $UiPort = 8501,

    [ValidateRange(1, 65535)]
    [int] $EmbeddingPort = 11435
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    if ($Service -eq 'embedding') {
        $env:OLLAMA_HOST = "127.0.0.1:$EmbeddingPort"
        $env:OLLAMA_MODELS = Join-Path $projectRoot '.research-agent/ollama-models'
        ollama serve
        exit $LASTEXITCODE
    }

    $runtimePython = Join-Path $projectRoot '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $runtimePython -PathType Leaf)) {
        throw 'Create the Python 3.12 virtual environment and install the project extras first.'
    }
    if ($Service -eq 'api') {
        if (-not $env:RESEARCH_EMBED_URL) {
            $env:RESEARCH_EMBED_URL = "http://127.0.0.1:$EmbeddingPort"
        }
        & $runtimePython -X utf8 -B -m uvicorn research_agent.app.api:app --host 127.0.0.1 --port $ApiPort
    } else {
        if (-not $env:RESEARCH_API_URL) {
            $env:RESEARCH_API_URL = "http://127.0.0.1:$ApiPort"
        }
        $interface = & $runtimePython -X utf8 -B -c "from importlib.util import find_spec; print(find_spec('research_agent.app.ui').origin)"
        if ($LASTEXITCODE -ne 0) {
            throw 'Install the project and its app extra first.'
        }
        & $runtimePython -X utf8 -B -m streamlit run $interface --server.address 127.0.0.1 --server.port $UiPort --server.headless true --server.maxUploadSize 12 --browser.gatherUsageStats false
    }
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
