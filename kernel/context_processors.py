from django.conf import settings


def static_version(request):
    return {"static_version": settings.STATIC_VERSION}
