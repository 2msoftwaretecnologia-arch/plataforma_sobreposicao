"""Realce de tiles de satélite ("Melhorar imagem" no painel do mapa).

Só deixa mais legível o que o sensor registrou: contraste, interpolação
suave e nitidez na escala do pixel original. Não é super-resolução (que
inventa textura e não serve de prova num laudo).

A nitidez (máscara de nitidez) olha os vizinhos de cada pixel; feita tile a
tile criaria emendas nas bordas. Por isso o tile é lido com uma margem
(`buffer`), realçado e só então recortado nos 256 px.
"""
import io
import math

import numpy as np
from PIL import Image, ImageFilter

TILE_SIZE = 256
EARTH_CIRCUMFERENCE = 2 * math.pi * 6378137

# Raio da máscara em pixels do pixel original do sensor: meio pixel realça a
# borda entre dois pixels vizinhos sem criar halo largo.
SHARPEN_RADIUS_FRACTION = 0.5
SHARPEN_MIN_RADIUS = 0.8
SHARPEN_MAX_RADIUS = 16
SHARPEN_PERCENT = 110
SHARPEN_THRESHOLD = 2


def tile_ground_pixel(z, y):
    """Metros no terreno por pixel do tile XYZ (na latitude do centro dele)."""
    n = 2 ** z
    lat = math.atan(math.sinh(math.pi * (1 - 2 * (y + 0.5) / n)))
    return EARTH_CIRCUMFERENCE * math.cos(lat) / (TILE_SIZE * n)


def sharpen_radius(source_res, z, y):
    """Raio da máscara (px do tile) para uma imagem de `source_res` metros."""
    source_px = source_res / tile_ground_pixel(z, y)
    return min(SHARPEN_MAX_RADIUS, max(SHARPEN_MIN_RADIUS, SHARPEN_RADIUS_FRACTION * source_px))


def sharpen_buffer(radius):
    """Margem (px) que a máscara de `radius` precisa para não ver a borda."""
    return int(math.ceil(3 * radius)) + 2


def sharpen_rgba(rgba, radius, buffer=0):
    """RGBA (array h×w×4 uint8) com nitidez no RGB, sem a margem `buffer`."""
    image = Image.fromarray(np.ascontiguousarray(rgba), 'RGBA')
    rgb = image.convert('RGB').filter(
        ImageFilter.UnsharpMask(radius=radius, percent=SHARPEN_PERCENT, threshold=SHARPEN_THRESHOLD))
    out = np.dstack([np.asarray(rgb), np.asarray(image)[:, :, 3]])
    if buffer:
        out = out[buffer:-buffer, buffer:-buffer]
    return np.ascontiguousarray(out)


def sharpen_png(content, radius, buffer=0):
    """PNG com nitidez, recortado sem a margem `buffer`."""
    rgba = np.asarray(Image.open(io.BytesIO(content)).convert('RGBA'))
    out = io.BytesIO()
    Image.fromarray(sharpen_rgba(rgba, radius, buffer), 'RGBA').save(out, format='PNG')
    return out.getvalue()
