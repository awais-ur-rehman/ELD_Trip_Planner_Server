from pathlib import Path

import environ

env = environ.Env()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-only-secret-key-change-before-production")
DEBUG      = env.bool("DEBUG", default=False)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "corsheaders",
    "apps.common",
    "apps.routing",
    "apps.eld",
    "apps.trips",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF      = "config.urls"
WSGI_APPLICATION  = "config.wsgi.application"

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://eld_user:eld_pass@localhost:5432/eld_planner",
    )
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://localhost:6379/0"),
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE     = "UTC"
USE_TZ        = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES":   ["rest_framework.parsers.JSONParser"],
    "EXCEPTION_HANDLER":        "rest_framework.views.exception_handler",
}

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=["http://localhost:3000"],
)
