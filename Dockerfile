# Imagem do gateway (aplicacao FastAPI/LangGraph deste repositorio) -- design.md Secao 5,
# servico `gateway` do docker-compose (`build: .`, porta interna 8000 -> 8080 no host).
FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY config ./config
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000"]
