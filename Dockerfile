FROM python:3.11.14

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    proj-bin \
    libspatialindex-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uwsgi

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

COPY uwsgi.ini /etc/uwsgi/uwsgi.ini

ENV GDAL_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/libgdal.so
ENV GEOS_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/libgeos_c.so

EXPOSE 8000

CMD ["uwsgi", "--ini", "/etc/uwsgi/uwsgi.ini"]

