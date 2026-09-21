FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c
RUN pip install --no-cache-dir grpcio==1.75.1 typing-extensions==4.16.0
WORKDIR /fixture
COPY server.py /fixture/server.py
USER 65532:65532
EXPOSE 8080 50051
ENV PYTHONUNBUFFERED=1
CMD ["python", "/fixture/server.py"]
