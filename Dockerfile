FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

RUN python -m pip install --upgrade pip build

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m build --wheel


FROM python:3.12-slim AS runtime

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system kube-saver \
    && adduser --system --ingroup kube-saver --home /app kube-saver

COPY --from=builder /build/dist/*.whl /tmp/

RUN python -m pip install --upgrade pip \
    && python -m pip install /tmp/*.whl \
    && rm -rf /tmp/*.whl /root/.cache/pip

USER kube-saver

ENTRYPOINT ["kube-saver"]
CMD ["version"]
