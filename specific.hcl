postgres "main" {}

storage "screenshots" {}

secret "anthropic_api_key" {
  dev {
    required = false
  }
}

secret "openai_api_key" {
  dev {
    required = false
  }
}

secret "mcp_caller_tokens" {
  dev {
    required = false
  }
}

build "cli" {
  base = "python"
}

# suth is invoked ad hoc (`specific exec cli -- .venv/bin/python run_test.py ...`),
# not a long-running server — this service block exists only so `specific dev`/`exec`
# provision Postgres + storage and inject their env vars. The idle command just keeps
# the dev process alive without doing anything.
service "cli" {
  build = build.cli
  command = ".venv/bin/python -c \"import time; time.sleep(1e9)\""

  env = {
    DATABASE_URL      = postgres.main.url
    S3_ENDPOINT       = storage.screenshots.endpoint
    S3_ACCESS_KEY     = storage.screenshots.access_key
    S3_SECRET_KEY     = storage.screenshots.secret_key
    S3_BUCKET         = storage.screenshots.bucket
    ANTHROPIC_API_KEY = secret.anthropic_api_key
    OPENAI_API_KEY    = secret.openai_api_key
    MCP_CALLER_TOKENS = secret.mcp_caller_tokens
  }
}

# Phase 5's Local Control API — a real long-running FastAPI service, unlike
# the idle "cli" placeholder above.
service "api" {
  build = build.cli
  command = ".venv/bin/uvicorn suth.api.app:app --host 0.0.0.0 --port $PORT"

  endpoint {
    public = true
    health_check {
      path = "/healthz"
    }
  }

  env = {
    PORT               = port
    DATABASE_URL        = postgres.main.url
    S3_ENDPOINT        = storage.screenshots.endpoint
    S3_ACCESS_KEY      = storage.screenshots.access_key
    S3_SECRET_KEY      = storage.screenshots.secret_key
    S3_BUCKET          = storage.screenshots.bucket
    ANTHROPIC_API_KEY  = secret.anthropic_api_key
    OPENAI_API_KEY     = secret.openai_api_key
    CORS_ORIGIN        = "https://${service.web.public_url}"
  }

  dev {
    command = ".venv/bin/uvicorn suth.api.app:app --host 0.0.0.0 --port $PORT --reload --reload-dir src"
    env = {
      CORS_ORIGIN = "http://${service.web.public_url}"
    }
  }
}

# The web app — a thin client over the Local Control API above (every panel
# calls the same REST/WebSocket endpoints), replacing the old native GUI.
build "web" {
  base = "node"
  root = "web"
  command = "npm run build"
}

service "web" {
  build = build.web
  command = "npm start"

  endpoint {
    public = true
  }

  env = {
    PORT    = port
    API_URL = "https://${service.api.public_url}"
  }

  dev {
    command = "npm run dev"
    env = {
      API_URL = "http://${service.api.public_url}"
    }
  }
}
