FROM python:3.12-slim-trixie AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

RUN python -m pip install --upgrade pip build

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m build --wheel


FROM python:3.12-slim-trixie AS runtime

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system kube-saver \
    && adduser --system --ingroup kube-saver --home /home/kube-saver kube-saver \
    && mkdir -p /home/kube-saver/.kube \
    && chown -R kube-saver:kube-saver /home/kube-saver

COPY --from=builder /build/dist/*.whl /tmp/
COPY constraints-image.txt /tmp/constraints-image.txt

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir --constraint /tmp/constraints-image.txt /tmp/*.whl \
    && python -m pip check \
    && python -m pip uninstall --yes pip \
    && rm -rf /tmp/*.whl /tmp/constraints-image.txt /root/.cache/pip \
        /usr/local/lib/python3.12/ensurepip

USER kube-saver

ENTRYPOINT ["kube-saver"]
CMD ["version"]
